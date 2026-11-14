"""Safe save/load keeps the state that later decisions read."""

from __future__ import annotations

import json
import pickle
import time

import pytest

from agent import Agent
from cortex import CortexMemory
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from labile_layer import PlasticityConfig
from learning_guard import initializing, labile_snapshot
from selector import ActionSelector
from sleep import SleepManager
from state_codec import AGENT_STATE_FORMAT, StateFormatError
from storage import AgentStorage


def _build_agent(actions, seed=0, wake_s=1000.0):
    hippocampus = NOWAHippocampus(max_experiences=80)
    cortex = CortexMemory()
    memory = IntentMemory()
    sleep_manager = SleepManager(hippocampus, cortex, memory)
    selector = ActionSelector(actions=list(actions))
    return Agent(
        hippocampus,
        cortex,
        selector,
        sleep_manager,
        memory,
        rng_seed=seed,
        plasticity_config=PlasticityConfig(expected_wake_interval_s=wake_s),
    )


def _load_into(storage, source_path, seed):
    restored = _build_agent(("go", "stop"), seed=seed)
    storage.load_agent(
        restored.hippocampus,
        restored.cortex,
        restored.selector,
        source_path,
        sleep_manager=restored.sleep_manager,
        value_layer=restored.value_layer,
        conflict_arbitration=restored.conflict_arbitration,
        intent_memory=restored.intent_memory,
        agent=restored,
    )
    return restored


def _signature_rows(hippocampus):
    rows = []
    for experience, signature in zip(hippocampus.experiences, hippocampus.signatures):
        rows.append({
            "episode_id": getattr(experience, "episode_id", None),
            "last_activated": float(experience.last_activated),
            "activation_energy": float(experience.activation_energy),
            "last_decay_ts": float(signature.last_decay_ts),
            "activation_weight": float(signature.activation_weight),
            "timestamp": float(signature.timestamp),
            "context_tokens": tuple(signature.context_tokens),
            "context_vector": tuple(float(item) for item in signature.context_vector),
            "features": tuple(sorted(signature.feature_set)),
            "same_object": signature.source_experience is experience,
        })
    return rows


def _decision(agent, context):
    intent_pressure = agent.intent_memory.activate_by_context(list(context))
    experiences = agent.hippocampus.activate(list(context))
    patterns = agent.cortex.activate(list(context))
    pressures = agent.selector.compute_pressures(experiences, patterns, intent_pressure)
    arbitration = agent.conflict_arbitration.arbitrate(
        go_signals=list(pressures.values()),
        prediction_error=0.0,
        policy_entropy=0.4,
        working_memory_load=0.3,
    )
    winner = max(pressures, key=pressures.get)
    return {
        "pressures": {key: float(value) for key, value in pressures.items()},
        "winner": winner,
        "experiences": [getattr(item, "episode_id", None) for item in experiences],
        "mode": arbitration.get("control_mode"),
        "control_cost": float(arbitration.get("control_cost", 0.0)),
        "weights": [float(sig.activation_weight) for sig in agent.hippocampus.signatures],
        "decay_ts": [float(sig.last_decay_ts) for sig in agent.hippocampus.signatures],
    }


def test_round_trip_keeps_decisions_and_does_not_decay_twice(tmp_path, monkeypatch):
    clock = {"t": 1_700_000_000.0}
    monkeypatch.setattr(time, "time", lambda: clock["t"])

    agent = _build_agent(("go", "stop"), seed=4)
    with initializing():
        agent.intent_memory.record_trace(["bin", "north"], "go")
        agent.intent_memory.record_trace(["bin", "north"], "go")
    agent.step(["bin", "north"], reward=1.0, terminal=True, dt=1.0)
    agent.step(["bin", "south"], reward=-0.4, terminal=True, dt=1.0)
    agent.step(["bin", "north"], reward=0.7, terminal=True, dt=1.0)
    agent.conflict_arbitration.error_history_window = [0.2, 0.85, 0.4]
    agent.conflict_arbitration.recent_failures = [1.0, 0.0, 1.0]
    agent.conflict_arbitration.recent_failure_rate = 2.0 / 3.0
    agent.conflict_arbitration.control_cost = 0.2
    clock["t"] += 3600.0
    agent.hippocampus._apply_decay()

    before = _signature_rows(agent.hippocampus)
    assert before
    assert all(row["same_object"] for row in before)
    assert any(row["last_decay_ts"] != row["last_activated"] for row in before)
    intent_before = agent.intent_memory.to_dict()
    arbitration_before = agent.conflict_arbitration.snapshot()
    labile_before = labile_snapshot(agent)

    storage = AgentStorage(save_dir=str(tmp_path))
    path = storage.save_agent(
        agent.hippocampus,
        agent.cortex,
        agent.selector,
        sleep_manager=agent.sleep_manager,
        value_layer=agent.value_layer,
        conflict_arbitration=agent.conflict_arbitration,
        intent_memory=agent.intent_memory,
        agent=agent,
        filename="roundtrip.nowa",
    )
    restored = _load_into(storage, path, seed=11)
    again = storage.save_agent(
        restored.hippocampus,
        restored.cortex,
        restored.selector,
        sleep_manager=restored.sleep_manager,
        value_layer=restored.value_layer,
        conflict_arbitration=restored.conflict_arbitration,
        intent_memory=restored.intent_memory,
        agent=restored,
        filename="roundtrip-again.nowa",
    )
    third = _load_into(storage, again, seed=12)

    assert _signature_rows(agent.hippocampus) == before
    assert _signature_rows(restored.hippocampus) == before
    assert _signature_rows(third.hippocampus) == before
    assert restored.intent_memory.to_dict() == intent_before
    assert third.conflict_arbitration.snapshot() == arbitration_before
    assert labile_snapshot(restored)["q"] == labile_before["q"]
    assert restored.hippocampus._feature_bits == agent.hippocampus._feature_bits
    assert restored.hippocampus._token_bits == agent.hippocampus._token_bits
    assert list(restored.hippocampus._recent_event_window) == list(agent.hippocampus._recent_event_window)
    assert restored.hippocampus._nov_valid is agent.hippocampus._nov_valid

    clock["t"] += 1800.0
    context = ["bin", "north"]
    live = _decision(agent, context)
    loaded = _decision(restored, context)
    assert loaded["pressures"] == pytest.approx(live["pressures"])
    assert loaded["winner"] == live["winner"]
    assert loaded["experiences"] == live["experiences"]
    assert loaded["mode"] == live["mode"]
    assert loaded["control_cost"] == pytest.approx(live["control_cost"])
    assert loaded["weights"] == pytest.approx(live["weights"])
    assert loaded["decay_ts"] == pytest.approx(live["decay_ts"])


def test_pickle_and_unknown_schema_are_rejected(tmp_path):
    storage = AgentStorage(save_dir=str(tmp_path))
    agent = _build_agent(("go",), seed=1)
    hippocampus = agent.hippocampus
    cortex = agent.cortex
    selector = agent.selector

    pickled = tmp_path / "old.pkl"
    pickled.write_bytes(pickle.dumps({"hippocampus_experiences": []}))
    with pytest.raises(StateFormatError, match="pickle"):
        storage.load_agent(hippocampus, cortex, selector, str(pickled))

    future = tmp_path / "future.nowa"
    future.write_text(json.dumps({
        "format": AGENT_STATE_FORMAT,
        "schema_version": 99,
        "state": {},
    }), encoding="utf-8")
    with pytest.raises(StateFormatError, match="schema version"):
        storage.load_agent(hippocampus, cortex, selector, str(future))

    foreign = tmp_path / "foreign.nowa"
    foreign.write_text(json.dumps({
        "format": "something-else",
        "schema_version": 1,
        "state": {},
    }), encoding="utf-8")
    with pytest.raises(StateFormatError, match="something-else"):
        storage.load_agent(hippocampus, cortex, selector, str(foreign))
