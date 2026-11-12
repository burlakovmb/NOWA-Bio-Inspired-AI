import json
import os
from datetime import datetime
import pickle
from affect import AffectiveState


def _bind_restored_two_tier(agent, sleep_manager) -> None:
    """Point sleep managers at the labile layer and plasticity now on ``agent``.

    ``load_agent`` replaces those objects. Consolidation reads the manager's
    own references first, so a stale empty layer would drop the restored
    tags. ``_host_agent`` is set only when it is missing or already this
    agent: ``Agent.__init__`` binds the manager to the cognitive host, and a
    cage that shares the manager must keep a different host it already has.
    Reference assignment only; learned weights are not written here.
    """
    if agent is None:
        return
    managers = []
    for manager in (sleep_manager, getattr(agent, "sleep_manager", None)):
        if manager is None or any(manager is seen for seen in managers):
            continue
        managers.append(manager)
    labile = getattr(agent, "labile", None)
    plasticity = getattr(agent, "plasticity", None)
    for manager in managers:
        try:
            if labile is not None:
                setattr(manager, "labile", labile)
            if plasticity is not None:
                setattr(manager, "plasticity", plasticity)
            if getattr(manager, "_host_agent", None) in (None, agent):
                setattr(manager, "_host_agent", agent)
        except Exception:
            pass


class AgentStorage:
    """Сохранение и загрузка состояния агента"""
    
    def __init__(self, save_dir="saves"):
        self.save_dir = save_dir
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
    
    def save_agent(self, hippocampus, cortex, selector, affect_state=None, temporal=None, sleep_manager=None, neuromodulators=None, affective_persistence=None, affective_background=None, affective_space=None, semantic_emotions=None, emotional_memory=None, emotional_expectations=None, emotional_regulation=None, emotional_stability=None, value_layer=None, filename=None, agent=None, conflict_arbitration=None):
        """Сохранить состояние агента в файл"""
        if filename is None:
            filename = f"agent_save_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl"
        if value_layer is None and agent is not None and hasattr(agent, "value_layer"):
            value_layer = getattr(agent, "value_layer", None)
        if conflict_arbitration is None and agent is not None and hasattr(agent, "conflict_arbitration"):
            conflict_arbitration = getattr(agent, "conflict_arbitration", None)
        
        filepath = os.path.join(self.save_dir, filename)
        
        # Сохранить все данные через pickle
        agent_state = {
            "hippocampus_experiences": hippocampus.experiences,
            "hippocampus_episode_seq": int(getattr(hippocampus, "_episode_seq", 0)),
            "cortex_patterns": cortex.patterns,
            "selector_actions": selector.actions,
            "selector_confidence_threshold": selector.confidence_threshold,
            "selector_action_metadata": dict(getattr(selector, "action_metadata", {}) or {}),
            "timestamp": datetime.now().isoformat()
        }
        
        # Сохранить аффективное состояние если оно есть (полная сериализация)
        if affect_state is not None:
            try:
                agent_state["affect_state"] = affect_state.to_dict()
            except Exception:
                # Fallback to minimal fields
                agent_state["affect_state"] = {
                    "valence": affect_state.valence,
                    "arousal": affect_state.arousal,
                    "threat": affect_state.threat,
                    "curiosity": affect_state.curiosity
                }

        # Сохранить temporal levels если доступны (включая полное содержимое T1)
        if temporal is not None:
            try:
                tl = temporal.get_levels()
                # Save full T1 contents (deque -> list) for exact restoration
                try:
                    t1_list = [dict(item) for item in list(getattr(temporal, "t1", []))]
                except Exception:
                    t1_list = []
                tl["t1_full"] = t1_list
                tl["window_size"] = getattr(temporal, "window_size", None)
                agent_state["temporal_levels"] = tl
            except Exception:
                pass

        # Сохранить состояние sleep_manager если доступно
        if sleep_manager is not None:
            try:
                sleep_data = {
                    "consolidation_cycles": getattr(sleep_manager, "consolidation_cycles", 0)
                }
                for attr_name in (
                    "replay_priority_weights",
                    "replay_budget_per_sleep",
                    "max_replay_per_episode",
                    "replay_priority_min",
                    "replay_priority_cap",
                    "replay_temperature_decay",
                    "ach_replay_gain",
                    "edpc_priority_enabled",
                    "edpc_consolidation_blend",
                    "shock_priority_gain",
                    "edpc_sac_ema_alpha",
                    "edpc_sac_stability_k1",
                    "edpc_sac_td_stability_gain",
                    "edpc_sac_energy_budget",
                    "edpc_sac_conflict_threshold",
                    "instability_variance_threshold",
                    "td_threshold",
                    "td_variance_cap",
                    "salience_threshold",
                    "min_reinforcement_for_consolidation",
                    "variance_gate_threshold",
                    "state_estimate_variance_threshold",
                    "ach_min_for_consolidation",
                    "stability_index_threshold",
                    "consolidation_cap",
                    "w_td",
                    "w_salience",
                    "w_importance",
                    "w_ach",
                    "w_encoding",
                    "sleep_alpha_cap",
                    "per_update_cap",
                    "max_l2_update_per_cycle",
                    "global_sleep_update_budget",
                    "td_clip_sleep",
                    "delta_value_max_per_sleep",
                    "value_total_cap",
                    "value_cap",
                    "alpha_sleep_ratio",
                    "dopamine_sleep_scale",
                    "beta_sleep",
                    "delta_weight_max_per_sleep",
                    "weight_total_cap",
                    "decay_rate_sleep",
                    "weight_norm_cap",
                    "last_sleep_replay_stats",
                    "last_sac_stats",
                    "sac_theta_conf",
                    "sac_theta_stab",
                    "sac_theta_shock",
                    "sac_theta_cons",
                    "sac_theta_min_weight",
                    "sac_alpha_slow",
                    "sac_epsilon_divergence",
                    "sac_epsilon_var",
                    "sac_sigma_floor",
                    "sac_replay_min_count",
                    "sac_shock_block_threshold",
                    "sac_shock_variance_threshold",
                    "sac_high_stability_threshold",
                    "sac_stability_variance_discount",
                    "sac_success_threshold",
                    "local_phase_mode",
                    "sac_theta_arousal_low",
                    "sac_theta_arousal_high",
                    "sac_theta_shock_low",
                    "sac_theta_shock_high",
                    "sac_theta_conf_high",
                    "sac_theta_cons_high",
                    "sac_theta_stability_high",
                    "sac_alpha_base",
                    "sac_alpha_sigma",
                    "sac_sigma_decay_sws",
                    "sac_epsilon_var_rem",
                    "sac_beta_stability_sws",
                    "sac_delta_rem",
                    "sac_stability_floor_rem",
                    "sac_lambda_sws",
                    "sac_lambda_rem",
                    "sac_semantic_confidence_step_cap",
                    "sac_theta_structural",
                    "sac_structural_alert_reset_cycles",
                ):
                    if hasattr(sleep_manager, attr_name):
                        sleep_data[attr_name] = getattr(sleep_manager, attr_name)
                # Сохранить цепочки (Plan B - Temporal Chains)
                if hasattr(sleep_manager, 'chain_memory') and sleep_manager.chain_memory:
                    sleep_data["chain_memory"] = sleep_manager.chain_memory.to_dict()
                agent_state["sleep_manager"] = sleep_data
            except Exception:
                pass

        # Save neuromodulators state if provided
        if neuromodulators is not None:
            try:
                agent_state['neuromodulators'] = getattr(neuromodulators, 'to_dict', lambda: neuromodulators)()
            except Exception:
                try:
                    agent_state['neuromodulators'] = dict(neuromodulators)
                except Exception:
                    pass

        # Save affective persistence traces if provided
        if affective_persistence is not None:
            try:
                agent_state["affective_persistence"] = getattr(affective_persistence, "to_dict", lambda: affective_persistence)()
            except Exception:
                try:
                    agent_state["affective_persistence"] = dict(affective_persistence)
                except Exception:
                    pass

        # Save affective background field if provided
        if affective_background is not None:
            try:
                agent_state["affective_background"] = getattr(affective_background, "to_dict", lambda: affective_background)()
            except Exception:
                try:
                    agent_state["affective_background"] = dict(affective_background)
                except Exception:
                    pass

        # Save affective space if provided
        if affective_space is not None:
            try:
                agent_state["affective_space"] = getattr(affective_space, "to_dict", lambda: affective_space)()
            except Exception:
                try:
                    agent_state["affective_space"] = dict(affective_space)
                except Exception:
                    pass

        # Save semantic emotions layer if provided
        if semantic_emotions is not None:
            try:
                agent_state["semantic_emotions"] = getattr(semantic_emotions, "to_dict", lambda: semantic_emotions)()
            except Exception:
                try:
                    agent_state["semantic_emotions"] = list(semantic_emotions)
                except Exception:
                    pass

        # Save emotional memory narratives if provided
        if emotional_memory is not None:
            try:
                agent_state["emotional_memory"] = getattr(emotional_memory, "to_dict", lambda: emotional_memory)()
            except Exception:
                try:
                    agent_state["emotional_memory"] = dict(emotional_memory)
                except Exception:
                    pass

        # Save emotional expectations if provided
        if emotional_expectations is not None:
            try:
                agent_state["emotional_expectations"] = getattr(emotional_expectations, "to_dict", lambda: emotional_expectations)()
            except Exception:
                try:
                    agent_state["emotional_expectations"] = dict(emotional_expectations)
                except Exception:
                    pass

        # Save emotional regulation if provided
        if emotional_regulation is not None:
            try:
                agent_state["emotional_regulation"] = getattr(emotional_regulation, "to_dict", lambda: emotional_regulation)()
            except Exception:
                try:
                    agent_state["emotional_regulation"] = dict(emotional_regulation)
                except Exception:
                    pass

        # Save conflict arbitration layer (ACC-like) if provided
        if conflict_arbitration is not None:
            try:
                agent_state["conflict_arbitration"] = getattr(
                    conflict_arbitration,
                    "to_dict",
                    lambda: conflict_arbitration,
                )()
            except Exception:
                try:
                    agent_state["conflict_arbitration"] = dict(conflict_arbitration)
                except Exception:
                    pass

        # Save emotional stability monitoring (Phase 4.5) if provided
        if emotional_stability is not None:
            try:
                agent_state["emotional_stability"] = getattr(emotional_stability, "to_dict", lambda: emotional_stability)()
            except Exception:
                try:
                    agent_state["emotional_stability"] = dict(emotional_stability)
                except Exception:
                    pass

        # Save value layer (Phase 5.0) if provided
        if value_layer is not None:
            try:
                agent_state["value_layer"] = getattr(value_layer, "to_dict", lambda: value_layer)()
            except Exception:
                try:
                    agent_state["value_layer"] = dict(value_layer)
                except Exception:
                    pass

        # Сохранить веса селектора, если они есть (совместимость)
        if hasattr(selector, "weights"):
            try:
                agent_state["selector_weights"] = dict(getattr(selector, "weights", {}))
            except Exception:
                pass

        # Save agent lifetime data if provided
        if agent is not None:
            try:
                channels_data = {}
                for action_id, channel in getattr(agent, "bg_action_channels", {}).items():
                    channels_data[str(action_id)] = {
                        "go_weight": float(getattr(channel, "go_weight", 0.5)),
                        "nogo_weight": float(getattr(channel, "nogo_weight", 0.5)),
                        "habit_strength": float(getattr(channel, "habit_strength", 0.0)),
                        "selection_count": int(getattr(channel, "selection_count", 0)),
                        "success_count": int(getattr(channel, "success_count", 0)),
                        "failure_count": int(getattr(channel, "failure_count", 0)),
                        "last_outcome": getattr(channel, "last_outcome", None),
                        "prior_go": float(getattr(channel, "prior_go", getattr(channel, "go_weight", 0.5))),
                        "prior_nogo": float(getattr(channel, "prior_nogo", getattr(channel, "nogo_weight", 0.5))),
                        "prior_habit": float(getattr(channel, "prior_habit", getattr(channel, "habit_strength", 0.0))),
                    }
                agent_state["bg_action_channels"] = channels_data
                agent_state["bg_sleep_memories"] = dict(getattr(agent, "bg_sleep_memories", {}))
                labile = getattr(agent, "labile", None)
                if labile is not None and hasattr(labile, "to_dict"):
                    agent_state["labile_layer"] = labile.to_dict()
                plasticity = getattr(agent, "plasticity", None)
                if plasticity is not None and hasattr(plasticity, "to_dict"):
                    agent_state["plasticity_config"] = plasticity.to_dict()
                try:
                    agent_state["host_clock_s"] = float(getattr(agent, "_host_clock_s", 0.0))
                except (TypeError, ValueError):
                    agent_state["host_clock_s"] = 0.0
                slots = getattr(agent, "_bg_outcome_slots", None)
                if isinstance(slots, dict):
                    agent_state["bg_outcome_slots"] = {
                        str(episode_id): [str(slot[0]), int(slot[1])]
                        for episode_id, slot in slots.items()
                        if isinstance(slot, tuple) and len(slot) == 2
                    }
                agent_state["agent_lifetime"] = {
                    "created_ts": getattr(agent, "created_ts", None),
                    "simulated_sleep_seconds": getattr(agent, "_simulated_sleep_seconds", 0.0),
                    "lived_steps": getattr(agent, "lived_steps", 0),
                    "expected_lifetime_steps": getattr(agent, "expected_lifetime_steps", None),
                }
                agent_state["last_episode_id"] = getattr(agent, "last_episode_id", None)
                agent_state["trajectory_seq"] = int(getattr(agent, "_trajectory_seq", 0))
                agent_state["trajectory_step"] = int(getattr(agent, "_trajectory_step", 0))
                agent_state["trajectory_id"] = getattr(agent, "_trajectory_id", None)
                agent_state["trajectory_closed"] = bool(getattr(agent, "_trajectory_closed", True))
                visit_counts = getattr(agent, "_action_visit_counts", None)
                if isinstance(visit_counts, dict):
                    portable_visits = {}
                    for key, count in visit_counts.items():
                        if not isinstance(key, tuple) or len(key) != 2:
                            continue
                        try:
                            portable_visits[(str(key[0]), str(key[1]))] = int(count)
                        except (TypeError, ValueError):
                            continue
                    agent_state["action_visit_counts"] = portable_visits

                # Save runtime counters for demo persistence
                agent_state["agent_runtime"] = {
                    "total_sim_time": float(getattr(agent, "total_sim_time", 0.0)),
                    "tick_count": int(getattr(agent, "tick_count", 0)),
                    "action_remaining_s": float(getattr(agent, "action_remaining_s", 0.0)),
                    "chain_cooldown_s": float(getattr(agent, "chain_cooldown_s", 0.0)),
                    "last_chain_name": getattr(agent, "last_chain_name", None),
                    "current_action": getattr(agent, "current_action", None),
                }

                # Save wakefulness state used by GUI fatigue panel and physiology logic.
                wakefulness_data = {}
                if hasattr(agent, "get_wakefulness_persistence_state"):
                    wakefulness_data = agent.get_wakefulness_persistence_state() or {}
                elif hasattr(agent, "wakefulness"):
                    wake = getattr(agent, "wakefulness")
                    wakefulness_data = {
                        "wakefulness": float(getattr(wake, "wakefulness", 0.0)),
                        "last_update_ts": float(getattr(wake, "last_update_ts", 0.0)),
                        "accumulated_waking_time": float(getattr(wake, "accumulated_waking_time", 0.0)),
                        "total_sleep_time": float(getattr(wake, "total_sleep_time", 0.0)),
                        "circadian_time_hours": float(getattr(wake, "circadian_time_hours", 0.0)),
                        "circadian_period_hours": float(getattr(wake, "circadian_period_hours", 24.0)),
                        "circadian_amplitude": float(getattr(wake, "circadian_amplitude", 0.3)),
                        "circadian_phase": float(getattr(wake, "circadian_phase", 0.0)),
                    }
                if isinstance(wakefulness_data, dict) and wakefulness_data:
                    agent_state["wakefulness"] = dict(wakefulness_data)

                # Save autonomous-organism runtime snapshot if it was initialized.
                auto_state = {}
                if hasattr(agent, "get_autonomous_state"):
                    auto_state = agent.get_autonomous_state() or {}
                if isinstance(auto_state, dict) and auto_state:
                    agent_state["autonomous_runtime"] = dict(auto_state)
            except Exception:
                pass
        
        with open(filepath, 'wb') as f:
            pickle.dump(agent_state, f)
        
        return filepath
    
    def load_agent(self, hippocampus, cortex, selector, filepath, affect_state=None, temporal=None, sleep_manager=None, neuromodulators=None, affective_persistence=None, affective_background=None, affective_space=None, semantic_emotions=None, emotional_memory=None, emotional_expectations=None, emotional_regulation=None, emotional_stability=None, value_layer=None, agent=None, conflict_arbitration=None):
        """Загрузить состояние агента из файла"""
        with open(filepath, 'rb') as f:
            agent_state = pickle.load(f)
        if value_layer is None and agent is not None and hasattr(agent, "value_layer"):
            value_layer = getattr(agent, "value_layer", None)
        if conflict_arbitration is None and agent is not None and hasattr(agent, "conflict_arbitration"):
            conflict_arbitration = getattr(agent, "conflict_arbitration", None)
        
        # Восстановить данные
        hippocampus.experiences = agent_state["hippocampus_experiences"]
        if hasattr(hippocampus, "_sync_episode_index"):
            try:
                hippocampus._sync_episode_index()
            except Exception:
                pass
        saved_seq = agent_state.get("hippocampus_episode_seq", 0)
        try:
            saved_seq = int(saved_seq)
        except (TypeError, ValueError):
            saved_seq = 0
        highest = 0
        if hasattr(hippocampus, "_highest_episode_seq"):
            try:
                highest = int(hippocampus._highest_episode_seq())
            except Exception:
                highest = 0
        if hasattr(hippocampus, "_episode_seq"):
            hippocampus._episode_seq = max(saved_seq, highest, int(getattr(hippocampus, "_episode_seq", 0)))
        cortex.patterns = agent_state["cortex_patterns"]
        # Селектор действий не имеет весов - это non-learnable компонент
        # Восстанавливаем только конфигурацию
        if "selector_actions" in agent_state:
            selector.actions = agent_state["selector_actions"]
        if "selector_confidence_threshold" in agent_state:
            selector.confidence_threshold = agent_state["selector_confidence_threshold"]
        if hasattr(selector, "action_metadata"):
            selector.action_metadata = {}
            if hasattr(selector, "_default_action_metadata"):
                for action in list(getattr(selector, "actions", [])):
                    try:
                        selector.action_metadata[str(action)] = selector._default_action_metadata(str(action))
                    except Exception:
                        pass
            for action_name, metadata in dict(agent_state.get("selector_action_metadata", {}) or {}).items():
                try:
                    if hasattr(selector, "set_action_metadata"):
                        selector.set_action_metadata(str(action_name), dict(metadata or {}))
                    else:
                        selector.action_metadata[str(action_name)] = dict(metadata or {})
                except Exception:
                    pass
        
        # Восстановить аффективное состояние если оно сохранено
        if affect_state is not None and "affect_state" in agent_state:
            affect_data = agent_state["affect_state"]
            try:
                # If dict was produced by AffectiveState.to_dict()
                reconstructed = AffectiveState.from_dict(affect_data)
                affect_state.valence = reconstructed.valence
                affect_state.arousal = reconstructed.arousal
                affect_state.threat = reconstructed.threat
                affect_state.curiosity = reconstructed.curiosity
                affect_state.attachment = reconstructed.attachment
                affect_state.affinity = reconstructed.affinity
                affect_state.aversion = reconstructed.aversion
                affect_state.timestamp = reconstructed.timestamp
            except Exception:
                # Fallback to minimal fields
                affect_state.valence = affect_data.get("valence", 0.0)
                affect_state.arousal = affect_data.get("arousal", 0.0)
                affect_state.threat = affect_data.get("threat", 0.0)
                affect_state.curiosity = affect_data.get("curiosity", 0.0)
        
        # Restore selector weights if available
        if hasattr(selector, "weights") and "selector_weights" in agent_state:
            try:
                selector.weights = dict(agent_state["selector_weights"])
            except Exception:
                pass

        # Restore temporal levels if provided
        if temporal is not None and "temporal_levels" in agent_state:
            try:
                tl = agent_state["temporal_levels"]
                # restore t0, t2, t3
                temporal.t0 = dict(tl.get("T0", {}))
                temporal.t2 = dict(tl.get("T2_baseline", {}))
                temporal.t3 = dict(tl.get("T3_attractor", {}))
                # restore full T1 if present
                from collections import deque
                t1_full = tl.get("t1_full")
                window_size = int(tl.get("window_size") or getattr(temporal, "window_size", 1))
                if t1_full and isinstance(t1_full, list):
                    temporal.t1 = deque([dict(item) for item in t1_full], maxlen=window_size)
                else:
                    # fallback: reconstruct from T1_mean
                    t1_mean = tl.get("T1_mean")
                    if t1_mean:
                        temporal.t1 = deque([dict(t1_mean) for _ in range(window_size)], maxlen=window_size)
            except Exception:
                pass

        # Restore sleep_manager state if provided
        if sleep_manager is not None and "sleep_manager" in agent_state:
            try:
                sleep_data = agent_state["sleep_manager"]
                sleep_manager.consolidation_cycles = sleep_data.get("consolidation_cycles", getattr(sleep_manager, "consolidation_cycles", 0))
                for attr_name in (
                    "replay_priority_weights",
                    "replay_budget_per_sleep",
                    "max_replay_per_episode",
                    "replay_priority_min",
                    "replay_priority_cap",
                    "replay_temperature_decay",
                    "ach_replay_gain",
                    "edpc_priority_enabled",
                    "edpc_consolidation_blend",
                    "shock_priority_gain",
                    "edpc_sac_ema_alpha",
                    "edpc_sac_stability_k1",
                    "edpc_sac_td_stability_gain",
                    "edpc_sac_energy_budget",
                    "edpc_sac_conflict_threshold",
                    "instability_variance_threshold",
                    "td_threshold",
                    "td_variance_cap",
                    "salience_threshold",
                    "min_reinforcement_for_consolidation",
                    "variance_gate_threshold",
                    "state_estimate_variance_threshold",
                    "ach_min_for_consolidation",
                    "stability_index_threshold",
                    "consolidation_cap",
                    "w_td",
                    "w_salience",
                    "w_importance",
                    "w_ach",
                    "w_encoding",
                    "sleep_alpha_cap",
                    "per_update_cap",
                    "max_l2_update_per_cycle",
                    "global_sleep_update_budget",
                    "td_clip_sleep",
                    "delta_value_max_per_sleep",
                    "value_total_cap",
                    "value_cap",
                    "alpha_sleep_ratio",
                    "dopamine_sleep_scale",
                    "beta_sleep",
                    "delta_weight_max_per_sleep",
                    "weight_total_cap",
                    "decay_rate_sleep",
                    "weight_norm_cap",
                    "last_sleep_replay_stats",
                    "last_sac_stats",
                    "sac_theta_conf",
                    "sac_theta_stab",
                    "sac_theta_shock",
                    "sac_theta_cons",
                    "sac_theta_min_weight",
                    "sac_alpha_slow",
                    "sac_epsilon_divergence",
                    "sac_epsilon_var",
                    "sac_sigma_floor",
                    "sac_replay_min_count",
                    "sac_shock_block_threshold",
                    "sac_shock_variance_threshold",
                    "sac_high_stability_threshold",
                    "sac_stability_variance_discount",
                    "sac_success_threshold",
                    "local_phase_mode",
                    "sac_theta_arousal_low",
                    "sac_theta_arousal_high",
                    "sac_theta_shock_low",
                    "sac_theta_shock_high",
                    "sac_theta_conf_high",
                    "sac_theta_cons_high",
                    "sac_theta_stability_high",
                    "sac_alpha_base",
                    "sac_alpha_sigma",
                    "sac_sigma_decay_sws",
                    "sac_epsilon_var_rem",
                    "sac_beta_stability_sws",
                    "sac_delta_rem",
                    "sac_stability_floor_rem",
                    "sac_lambda_sws",
                    "sac_lambda_rem",
                    "sac_semantic_confidence_step_cap",
                    "sac_theta_structural",
                    "sac_structural_alert_reset_cycles",
                ):
                    if attr_name in sleep_data:
                        setattr(sleep_manager, attr_name, sleep_data.get(attr_name))
                # Восстановить цепочки (Plan B - Temporal Chains)
                if hasattr(sleep_manager, 'chain_memory') and "chain_memory" in sleep_data:
                    sleep_manager.chain_memory.from_dict(sleep_data["chain_memory"])
            except Exception:
                pass

        # Restore neuromodulators if provided
        if "neuromodulators" in agent_state:
            try:
                nm_data = agent_state["neuromodulators"]
                if neuromodulators is not None:
                    try:
                        restored = type(neuromodulators).from_dict(nm_data)
                        for attr_name, attr_value in vars(restored).items():
                            try:
                                setattr(neuromodulators, attr_name, attr_value)
                            except Exception:
                                pass
                    except Exception:
                        try:
                            for k, v in dict(nm_data).items():
                                try:
                                    setattr(neuromodulators, k, v)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                # If caller provided sleep_manager or other place to attach, try to set
                if sleep_manager is not None and hasattr(sleep_manager, 'neuromodulators'):
                    try:
                        sleep_manager.neuromodulators = type(sleep_manager.neuromodulators).from_dict(nm_data)
                    except Exception:
                        try:
                            sleep_manager.neuromodulators = nm_data
                        except Exception:
                            pass
                # Also try to attach to hippocampus/cortex if they expect it
            except Exception:
                pass

        # Restore affective persistence if provided
        if affective_persistence is not None and "affective_persistence" in agent_state:
            try:
                ap_data = agent_state["affective_persistence"]
                # Prefer from_dict if available
                if hasattr(affective_persistence, "from_dict"):
                    restored = type(affective_persistence).from_dict(ap_data)
                    affective_persistence._traces = restored._traces
                    affective_persistence.default_decay_rate = restored.default_decay_rate
                    affective_persistence.decay_rate_range = restored.decay_rate_range
                    affective_persistence.accumulation_gain = restored.accumulation_gain
                    affective_persistence.min_intensity = restored.min_intensity
                else:
                    try:
                        affective_persistence.update(ap_data)
                    except Exception:
                        pass
            except Exception:
                pass

        # Restore affective background if provided
        if affective_background is not None and "affective_background" in agent_state:
            try:
                ab_data = agent_state["affective_background"]
                if hasattr(affective_background, "from_dict"):
                    restored = type(affective_background).from_dict(ab_data)
                    affective_background.background = dict(restored.background)
                    affective_background.base_inertia = restored.base_inertia
                    affective_background.k_life = restored.k_life
                    affective_background.base_decay = restored.base_decay
                    affective_background.k_decay = restored.k_decay
                    affective_background.base_sharpness = restored.base_sharpness
                    affective_background.k_comp = restored.k_comp
                    affective_background.noise_scale = restored.noise_scale
                else:
                    try:
                        affective_background.update(ab_data)
                    except Exception:
                        pass
            except Exception:
                pass

        # Restore affective space if provided
        if affective_space is not None and "affective_space" in agent_state:
            try:
                as_data = agent_state["affective_space"]
                if hasattr(affective_space, "from_dict"):
                    restored = type(affective_space).from_dict(as_data)
                    affective_space.axes = dict(restored.axes)
                    affective_space.baseline = dict(getattr(restored, "baseline", {}))
                    affective_space.alpha = float(getattr(restored, "alpha", getattr(affective_space, "alpha", 0.85)))
                    axis_decay_source = getattr(restored, "axis_decay", getattr(restored, "affective_decay", {}))
                    if hasattr(affective_space, "_fill_axis_decay"):
                        affective_space.axis_decay = affective_space._fill_axis_decay(
                            axis_decay_source,
                            fallback=affective_space.alpha,
                        )
                    elif isinstance(axis_decay_source, dict):
                        affective_space.axis_decay = dict(axis_decay_source)
                    else:
                        affective_space.axis_decay = {}
                    affective_space.affective_decay = dict(getattr(affective_space, "axis_decay", {}))
                    affective_space.lambda_reg = float(
                        getattr(restored, "lambda_reg", getattr(affective_space, "lambda_reg", 0.05))
                    )
                    affective_space.baseline_adapt_rate = float(
                        getattr(restored, "baseline_adapt_rate", getattr(affective_space, "baseline_adapt_rate", 0.002))
                    )
                    affective_space.norm_cap_base = float(
                        getattr(restored, "norm_cap_base", getattr(affective_space, "norm_cap_base", 1.5))
                    )
                    affective_space.norm_cap_max = float(
                        getattr(restored, "norm_cap_max", getattr(affective_space, "norm_cap_max", 2.2))
                    )
                    affective_space.norm_cap_adapt_rate = float(
                        getattr(restored, "norm_cap_adapt_rate", getattr(affective_space, "norm_cap_adapt_rate", 0.06))
                    )
                    affective_space.norm_cap_release_rate = float(
                        getattr(restored, "norm_cap_release_rate", getattr(affective_space, "norm_cap_release_rate", 0.02))
                    )
                    affective_space.norm_cap_global_release_rate = float(
                        getattr(
                            restored,
                            "norm_cap_global_release_rate",
                            getattr(affective_space, "norm_cap_global_release_rate", 0.005),
                        )
                    )
                    affective_space.dynamic_norm_cap = float(
                        getattr(restored, "dynamic_norm_cap", getattr(affective_space, "dynamic_norm_cap", affective_space.norm_cap_base))
                    )
                    affective_space.legacy_compat_weight = float(
                        getattr(restored, "legacy_compat_weight", getattr(affective_space, "legacy_compat_weight", 0.0))
                    )
                    affective_space.decay = dict(restored.decay)
                    affective_space.inertia = dict(restored.inertia)
                    affective_space.noise_sigma = dict(restored.noise_sigma)
                    affective_space.fall_rate = dict(restored.fall_rate)
                    affective_space.decision_matrix = dict(getattr(restored, "decision_matrix", {}))
                    affective_space.last_external_mean_impulse = float(
                        getattr(restored, "last_external_mean_impulse", getattr(affective_space, "last_external_mean_impulse", 0.0))
                    )
                    affective_space.timestamp = restored.timestamp
                else:
                    try:
                        affective_space.update(as_data)
                    except Exception:
                        pass
            except Exception:
                pass

        # Canon wins: loaded affect_state is a projection of A(t), never the reverse.
        if affective_space is not None and affect_state is not None and "affective_space" in agent_state:
            try:
                axes = dict(getattr(affective_space, "axes", {}) or {})
                if hasattr(affect_state, "valence"):
                    affect_state.valence = float(axes.get("valence", getattr(affect_state, "valence", 0.0)))
                if hasattr(affect_state, "arousal"):
                    affect_state.arousal = max(0.0, (float(axes.get("arousal", 0.0)) + 1.0))
                if hasattr(affect_state, "threat"):
                    affect_state.threat = max(0.0, min(1.0, float(axes.get("stress", getattr(affect_state, "threat", 0.0)))))
                if hasattr(affect_state, "curiosity"):
                    affect_state.curiosity = max(0.0, min(1.0, float(axes.get("curiosity", getattr(affect_state, "curiosity", 0.0)))))
            except Exception:
                pass
        if agent is not None and hasattr(agent, "_project_legacy_affect_from_affective_space"):
            try:
                agent._project_legacy_affect_from_affective_space(blend=1.0)
            except Exception:
                pass

        # Restore semantic emotions if provided
        if semantic_emotions is not None and "semantic_emotions" in agent_state:
            try:
                se_data = agent_state["semantic_emotions"]
                if hasattr(semantic_emotions, "from_dict"):
                    restored = type(semantic_emotions).from_dict(se_data)
                    semantic_emotions.active_emotions = list(getattr(restored, "active_emotions", []))
                    semantic_emotions.activation_threshold = getattr(restored, "activation_threshold", getattr(semantic_emotions, "activation_threshold", 0.0))
                    semantic_emotions.inertia_high_threshold = getattr(restored, "inertia_high_threshold", getattr(semantic_emotions, "inertia_high_threshold", 0.6))
                    semantic_emotions.fall_rate_low_threshold = getattr(restored, "fall_rate_low_threshold", getattr(semantic_emotions, "fall_rate_low_threshold", 0.3))
                    semantic_emotions.focus_high_threshold = getattr(restored, "focus_high_threshold", getattr(semantic_emotions, "focus_high_threshold", 0.6))
                    semantic_emotions.last_update_ts = getattr(restored, "last_update_ts", getattr(semantic_emotions, "last_update_ts", None))
                else:
                    try:
                        semantic_emotions.active_emotions = list(se_data)
                    except Exception:
                        pass
            except Exception:
                pass

        # Restore emotional memory narratives if provided
        if emotional_memory is not None and "emotional_memory" in agent_state:
            try:
                em_data = agent_state["emotional_memory"]
                if hasattr(emotional_memory, "from_dict"):
                    restored = type(emotional_memory).from_dict(em_data)
                    emotional_memory.episodes = list(getattr(restored, "episodes", []))
                    emotional_memory.patterns = list(getattr(restored, "patterns", []))
                    emotional_memory.narrative_fragments = list(getattr(restored, "narrative_fragments", []))
                    emotional_memory.character_traits = list(getattr(restored, "character_traits", []))
                    emotional_memory.last_update_ts = getattr(restored, "last_update_ts", getattr(emotional_memory, "last_update_ts", None))
                else:
                    try:
                        emotional_memory.update(em_data)
                    except Exception:
                        pass
            except Exception:
                pass

        # Restore emotional expectations if provided
        if emotional_expectations is not None and "emotional_expectations" in agent_state:
            try:
                ee_data = agent_state["emotional_expectations"]
                if hasattr(emotional_expectations, "from_dict"):
                    restored = type(emotional_expectations).from_dict(ee_data)
                    emotional_expectations.expectations = list(getattr(restored, "expectations", []))
                    emotional_expectations.dominant_forecast = getattr(restored, "dominant_forecast", "")
                    emotional_expectations.global_outlook = getattr(restored, "global_outlook", "stabilizing")
                    emotional_expectations.last_update_ts = getattr(restored, "last_update_ts", getattr(emotional_expectations, "last_update_ts", None))
                else:
                    try:
                        emotional_expectations.update(ee_data)
                    except Exception:
                        pass
            except Exception:
                pass

        # Restore emotional regulation if provided
        if emotional_regulation is not None and "emotional_regulation" in agent_state:
            try:
                er_data = agent_state["emotional_regulation"]
                if hasattr(emotional_regulation, "from_dict"):
                    restored = type(emotional_regulation).from_dict(er_data)
                    for attr_name in (
                        # CER core state
                        "decay_v",
                        "decay_a",
                        "decay_u",
                        "ema_alpha",
                        "sustained_prediction_error",
                        "valence",
                        "arousal",
                        "uncertainty_tension",
                        "chronic_negative_valence",
                        "depressive_bias",
                        "recovery_mode",
                        "negative_valence_steps",
                        "high_arousal_steps",
                        "step_count",
                        "runaway_activations",
                        "saturation_guard_activations",
                        "last_update_ts",
                        "last_time_delta",
                        "modulation_factors",
                        "neuromodulator_guidance",
                        # Backward compatibility fields
                        "regulation_active",
                        "regulation_mode",
                        "applied_adjustments",
                        "last_target_emotion",
                        "last_global_outlook",
                    ):
                        if hasattr(restored, attr_name):
                            setattr(emotional_regulation, attr_name, getattr(restored, attr_name))
                else:
                    try:
                        emotional_regulation.update(er_data)
                    except Exception:
                        pass
            except Exception:
                pass

        # Restore conflict arbitration layer (ACC-like) if provided
        if conflict_arbitration is not None and "conflict_arbitration" in agent_state:
            try:
                ca_data = agent_state["conflict_arbitration"]
                if hasattr(conflict_arbitration, "from_dict"):
                    restored = type(conflict_arbitration).from_dict(ca_data)
                    for attr_name, attr_value in vars(restored).items():
                        try:
                            setattr(conflict_arbitration, attr_name, attr_value)
                        except Exception:
                            pass
                else:
                    try:
                        conflict_arbitration.update(ca_data)
                    except Exception:
                        pass
            except Exception:
                pass

        # Restore emotional stability monitoring (Phase 4.5) if provided
        if emotional_stability is not None and "emotional_stability" in agent_state:
            try:
                es_data = agent_state["emotional_stability"]
                if hasattr(emotional_stability, "from_dict"):
                    restored = type(emotional_stability).from_dict(es_data)
                    for attr_name in (
                        "window_size",
                        "hysteresis_windows",
                        "baseline_background",
                        "baseline_neuromodulators",
                        "weights",
                        "stability_index",
                        "drift_flags",
                        "recommendation",
                        "metrics",
                        "last_update_ts",
                        "_regulation_active_history",
                        "_background_anxiety_history",
                        "_neuromodulator_histories",
                        "_outlook_history",
                        "_dominant_emotion_history",
                        "_dominant_intensity_history",
                        "_trigger_history",
                        "_hysteresis_counts",
                    ):
                        if hasattr(restored, attr_name):
                            setattr(emotional_stability, attr_name, getattr(restored, attr_name))
                else:
                    try:
                        emotional_stability.update(es_data)
                    except Exception:
                        pass
            except Exception:
                pass

        # Restore value layer (Phase 5.0) if provided
        if value_layer is not None and "value_layer" in agent_state:
            try:
                vl_data = agent_state["value_layer"]
                if hasattr(value_layer, "from_dict"):
                    restored = type(value_layer).from_dict(vl_data)
                    for attr_name in (
                        "max_states",
                        "alpha_default",
                        "alpha_online_default",
                        "alpha_sleep_default",
                        "alpha_sleep_ratio",
                        "ach_alpha_gain",
                        "alpha_online_soft_cap",
                        "gamma_default",
                        "dopamine_scale",
                        "reward_scale",
                        "max_update_l2",
                        "td_clip_online",
                        "adaptive_td_clip_enabled",
                        "td_clip_target_rate",
                        "td_clip_adapt_rate",
                        "td_clip_ema_beta",
                        "td_clip_min_online",
                        "td_clip_max_online",
                        "expectation_ema_beta",
                        "expectation_var_ema_beta",
                        "confirmation_threshold",
                        "confirmation_decay",
                        "confidence_k1",
                        "confidence_k2",
                        "stability_growth_rate",
                        "stability_decay_rate",
                        "stability_damping",
                        "shock_confidence_threshold",
                        "shock_delta_threshold",
                        "shock_plasticity_boost",
                        "shock_replay_gain",
                        "shock_frequency_beta",
                        "alpha_trajectory_window",
                        "td_layer",
                        "encoder",
                        "values",
                        "expectation_memory",
                        "last_update_ts",
                        "last_state_key",
                        "last_next_state_key",
                        "last_td_error",
                        "last_value",
                        "last_dopamine_delta",
                        "last_reward_raw",
                        "last_reward_scaled",
                        "last_delta_raw",
                        "last_delta_modulated",
                        "last_delta_clipped",
                        "last_td_was_clipped",
                        "last_td_clip_value_used",
                        "last_abs_delta",
                        "last_delta_sign",
                        "last_tonic_level",
                        "last_exploration_delta",
                        "online_td_clip_count",
                        "online_td_clip_updates",
                        "online_td_clip_frequency",
                        "online_td_clip_frequency_ema",
                        "last_alpha_effective",
                        "last_acetylcholine",
                        "last_expected_reward_mean",
                        "last_expected_reward_var",
                        "last_confirmation_count",
                        "last_confidence_score",
                        "last_stability_score",
                        "last_surprise",
                        "last_prediction_shock",
                        "last_replay_priority",
                        "last_consolidation_weight",
                        "shock_count_total",
                        "shock_frequency_ema",
                        "alpha_effective_trajectory",
                        "update_count",
                        "online_update_count",
                        "sleep_update_count",
                    ):
                        if hasattr(restored, attr_name):
                            setattr(value_layer, attr_name, getattr(restored, attr_name))
                else:
                    try:
                        value_layer.update(vl_data)
                    except Exception:
                        pass
            except Exception:
                pass

        # Restore BG channels and pending sleep memories if provided
        if agent is not None and "bg_action_channels" in agent_state:
            try:
                from basal_ganglia import ActionChannel

                restored_channels = {}
                for action_id, channel_data in dict(agent_state.get("bg_action_channels", {})).items():
                    ch = ActionChannel(
                        action_id=str(action_id),
                        go_weight=float(channel_data.get("go_weight", 0.5)),
                        nogo_weight=float(channel_data.get("nogo_weight", 0.5)),
                        habit_strength=float(channel_data.get("habit_strength", 0.0)),
                        prior_go=channel_data.get("prior_go"),
                        prior_nogo=channel_data.get("prior_nogo"),
                        prior_habit=channel_data.get("prior_habit"),
                    )
                    ch.selection_count = int(channel_data.get("selection_count", 0))
                    ch.success_count = int(channel_data.get("success_count", 0))
                    ch.failure_count = int(channel_data.get("failure_count", 0))
                    ch.last_outcome = channel_data.get("last_outcome")
                    restored_channels[ch.action_id] = ch
                agent.bg_action_channels = restored_channels
                if sleep_manager is not None:
                    try:
                        sleep_manager.bg_action_channels = agent.bg_action_channels
                    except Exception:
                        pass
            except Exception:
                pass

        if agent is not None and "bg_sleep_memories" in agent_state:
            try:
                agent.bg_sleep_memories = dict(agent_state.get("bg_sleep_memories", {}))
            except Exception:
                pass

        if agent is not None:
            try:
                from labile_layer import LabileLayer, PlasticityConfig

                if isinstance(agent_state.get("plasticity_config"), dict):
                    agent.plasticity = PlasticityConfig.from_dict(agent_state.get("plasticity_config"))
                if isinstance(agent_state.get("labile_layer"), dict):
                    agent.labile = LabileLayer.from_dict(agent_state.get("labile_layer"))
                    if getattr(agent, "plasticity", None) is not None:
                        agent.labile.config = agent.plasticity
                elif not isinstance(agent_state.get("labile_layer"), dict):
                    # Saves written before the labile tier load as an empty layer.
                    config = getattr(agent, "plasticity", None) or PlasticityConfig()
                    agent.plasticity = config
                    agent.labile = LabileLayer(config)
                if "host_clock_s" in agent_state:
                    agent._host_clock_s = float(agent_state.get("host_clock_s", 0.0))
                raw_slots = agent_state.get("bg_outcome_slots")
                if isinstance(raw_slots, dict):
                    agent._bg_outcome_slots = {
                        str(episode_id): (str(slot[0]), int(slot[1]))
                        for episode_id, slot in raw_slots.items()
                        if isinstance(slot, (list, tuple)) and len(slot) == 2
                    }
            except Exception:
                pass
            _bind_restored_two_tier(agent, sleep_manager)

        # Restore agent lifetime if provided
        if agent is not None and "agent_lifetime" in agent_state:
            try:
                life = agent_state.get("agent_lifetime", {})
                created_ts = life.get("created_ts")
                if created_ts is not None:
                    agent.created_ts = created_ts
                agent._simulated_sleep_seconds = float(life.get("simulated_sleep_seconds", 0.0))
                if "lived_steps" in life:
                    agent.lived_steps = int(life.get("lived_steps", 0))
                if "expected_lifetime_steps" in life and life.get("expected_lifetime_steps") is not None:
                    agent.expected_lifetime_steps = int(life.get("expected_lifetime_steps"))
            except Exception:
                pass

        if agent is not None and "last_episode_id" in agent_state:
            agent.last_episode_id = agent_state.get("last_episode_id")
        if agent is not None and "trajectory_seq" in agent_state:
            try:
                agent._trajectory_seq = int(agent_state.get("trajectory_seq", 0))
                agent._trajectory_step = int(agent_state.get("trajectory_step", 0))
                raw_trajectory = agent_state.get("trajectory_id")
                agent._trajectory_id = None if raw_trajectory in (None, "") else str(raw_trajectory)
                agent._trajectory_closed = bool(agent_state.get("trajectory_closed", True))
            except (TypeError, ValueError):
                pass
        if agent is not None and isinstance(agent_state.get("action_visit_counts"), dict):
            restored_visits = {}
            for key, count in agent_state.get("action_visit_counts", {}).items():
                if isinstance(key, tuple) and len(key) == 2:
                    restored_visits[(str(key[0]), str(key[1]))] = int(count)
            agent._action_visit_counts = restored_visits

        # Restore runtime counters if provided
        if agent is not None and "agent_runtime" in agent_state:
            try:
                runtime = agent_state.get("agent_runtime", {}) or {}
                if hasattr(agent, "total_sim_time"):
                    agent.total_sim_time = float(runtime.get("total_sim_time", agent.total_sim_time))
                if hasattr(agent, "tick_count"):
                    agent.tick_count = int(runtime.get("tick_count", agent.tick_count))
                if hasattr(agent, "action_remaining_s"):
                    agent.action_remaining_s = float(runtime.get("action_remaining_s", agent.action_remaining_s))
                if hasattr(agent, "chain_cooldown_s"):
                    agent.chain_cooldown_s = float(runtime.get("chain_cooldown_s", agent.chain_cooldown_s))
                if hasattr(agent, "last_chain_name"):
                    agent.last_chain_name = runtime.get("last_chain_name", agent.last_chain_name)
                if hasattr(agent, "current_action"):
                    agent.current_action = runtime.get("current_action", agent.current_action)
            except Exception:
                pass

        # Restore wakefulness runtime state if provided
        if agent is not None and "wakefulness" in agent_state:
            try:
                wake_data = agent_state.get("wakefulness", {}) or {}
                restored = False
                if hasattr(agent, "restore_wakefulness_persistence_state"):
                    restored = bool(agent.restore_wakefulness_persistence_state(wake_data))
                if not restored and hasattr(agent, "wakefulness"):
                    wake = getattr(agent, "wakefulness")
                    wake.wakefulness = float(wake_data.get("wakefulness", wake_data.get("current", 0.0)))
                    wake.last_update_ts = float(wake_data.get("last_update_ts", getattr(wake, "last_update_ts", 0.0)))
                    wake.accumulated_waking_time = float(
                        wake_data.get(
                            "accumulated_waking_time",
                            float(wake_data.get("accumulated_waking_hours", 0.0)) * 3600.0,
                        )
                    )
                    wake.total_sleep_time = float(
                        wake_data.get(
                            "total_sleep_time",
                            float(wake_data.get("total_sleep_hours", 0.0)) * 3600.0,
                        )
                    )
                    if hasattr(wake, "circadian_time_hours"):
                        wake.circadian_time_hours = float(
                            wake_data.get("circadian_time_hours", getattr(wake, "circadian_time_hours", 0.0))
                        )
                    if hasattr(wake, "circadian_period_hours"):
                        wake.circadian_period_hours = max(
                            1e-6,
                            float(wake_data.get("circadian_period_hours", getattr(wake, "circadian_period_hours", 24.0))),
                        )
                    if hasattr(wake, "circadian_amplitude"):
                        wake.circadian_amplitude = max(
                            0.0,
                            float(wake_data.get("circadian_amplitude", getattr(wake, "circadian_amplitude", 0.3))),
                        )
                    if hasattr(wake, "circadian_phase"):
                        wake.circadian_phase = float(
                            wake_data.get("circadian_phase", getattr(wake, "circadian_phase", 0.0))
                        )
            except Exception:
                pass

        # Restore autonomous runtime state if provided
        if agent is not None and "autonomous_runtime" in agent_state:
            try:
                auto_data = agent_state.get("autonomous_runtime", {}) or {}
                if hasattr(agent, "restore_autonomous_state"):
                    agent.restore_autonomous_state(auto_data, force_recreate=True)
            except Exception:
                pass

        return agent_state.get("timestamp")
    
    def get_save_files(self):
        """Получить список сохраненных файлов"""
        if not os.path.exists(self.save_dir):
            return []
        
        files = []
        for f in os.listdir(self.save_dir):
            if f.endswith('.pkl'):
                filepath = os.path.join(self.save_dir, f)
                files.append({
                    'name': f,
                    'path': filepath,
                    'modified': datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
                })
        
        return sorted(files, key=lambda x: x['modified'], reverse=True)
    
    def delete_save(self, filepath):
        """Удалить файл сохранения"""
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False
    
    def save_chat_history(self, history, filename=None):
        """Сохранить историю диалога"""
        if filename is None:
            filename = f"chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = os.path.join(self.save_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                "messages": history,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
        
        return filepath
    
    def load_chat_history(self, filepath):
        """Загрузить историю диалога"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return data.get("messages", [])
