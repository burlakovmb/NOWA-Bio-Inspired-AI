"""Failure boundaries for the optional sandbox habits checkpoint extension."""

import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from nowa_sandbox import sandbox_checkpoint as checkpoint
from nowa_sandbox.training_loop import SandboxTrainingResult
from state_codec import (
    AGENT_STATE_FORMAT,
    AGENT_STATE_SCHEMA_VERSION,
    StateFormatError,
    dump_state,
    load_state,
)


def _write(path, state):
    dump_state(
        path,
        state,
        format_id=AGENT_STATE_FORMAT,
        schema_version=AGENT_STATE_SCHEMA_VERSION,
    )


def _read(path):
    return load_state(
        path,
        expected_format=AGENT_STATE_FORMAT,
        supported_versions=(AGENT_STATE_SCHEMA_VERSION,),
    )


@pytest.fixture
def saved_state(tmp_path):
    path = tmp_path / "sandbox.agent.nowa"
    state = {"fallback": True, "experiences": ["synthetic-observation"]}
    _write(path, state)
    return path, path.read_bytes()


def _agent(payload=None):
    memory = SimpleNamespace(to_dict=lambda: payload if payload is not None else {"traces": []})
    return SimpleNamespace(
        hippocampus=SimpleNamespace(experiences=[]),
        intent_memory=memory,
        sleep_manager=SimpleNamespace(intent_memory=memory),
    )


def _metadata(path):
    return checkpoint.SandboxCheckpoint(
        last_quarter=0, graduated=False, graduated_at_quarter=None,
        result=SandboxTrainingResult(), agent_state_path=str(path),
    )


def test_extension_is_serialized_before_the_live_file_is_replaced(saved_state, monkeypatch):
    import state_codec

    path, original = saved_state
    real_replace = state_codec.os.replace
    calls = []

    def observed_replace(src, dst):
        assert Path(dst).read_bytes() == original
        assert os.path.abspath(src) != os.path.abspath(dst)
        calls.append(src)
        return real_replace(src, dst)

    monkeypatch.setattr(state_codec.os, "replace", observed_replace)
    checkpoint._save_intent_memory_extension(_agent(), path)

    assert len(calls) == 1
    assert _read(path)["sandbox_intent_memory"] == {"traces": []}
    assert list(path.parent.iterdir()) == [path]


def test_partial_serialization_failure_keeps_live_file_and_removes_temp(saved_state, monkeypatch):
    import state_codec

    path, original = saved_state

    def broken_dumps(*args, **kwargs):
        raise OSError("synthetic serialization failure")

    monkeypatch.setattr(state_codec.json, "dumps", broken_dumps)
    with pytest.raises(OSError, match="synthetic serialization failure"):
        checkpoint._save_intent_memory_extension(_agent(), path)
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("failure", ["replace", "fsync"])
def test_publish_failure_preserves_live_file_and_cleans_temp(saved_state, monkeypatch, failure):
    import state_codec

    path, original = saved_state

    def fail(*args):
        raise PermissionError("synthetic publish failure")

    monkeypatch.setattr(state_codec.os, failure, fail)
    with pytest.raises(PermissionError, match="synthetic publish failure"):
        checkpoint._save_intent_memory_extension(_agent(), path)
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]


def test_failed_memory_conversion_does_not_touch_live_file(saved_state):
    path, original = saved_state
    agent = _agent()

    def fail():
        raise ValueError("synthetic conversion failure")

    agent.intent_memory.to_dict = fail
    with pytest.raises(ValueError, match="synthetic conversion failure"):
        checkpoint._save_intent_memory_extension(agent, path)
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("payload", [
    None, "broken", [], {"traces": 17}, {"traces": "broken"},
    {"traces": [None]}, {"traces": [{"intent_type": "wait"}]},
    {"traces": {"legacy-key": "corrupt-row"}},
    {"traces": [{"intent_type": "wait", "context_signature": " "}]},
    {"traces": [{"intent_type": "wait", "context_signature": "context", "context_features": 17}]},
])
def test_invalid_optional_extension_keeps_base_restore_and_existing_habits(
    saved_state, payload, caplog,
):
    path, _ = saved_state
    state = _read(path)
    state["sandbox_intent_memory"] = payload
    _write(path, state)
    agent = _agent()
    previous = agent.intent_memory

    with caplog.at_level(logging.WARNING, logger=checkpoint.__name__):
        assert checkpoint.restore_agent(_metadata(path), agent) is True
    assert agent.hippocampus.experiences == ["synthetic-observation"]
    assert agent.intent_memory is previous
    assert agent.sleep_manager.intent_memory is previous
    assert "IntentMemory extension" in caplog.text


@pytest.mark.parametrize("failure", [OSError, EOFError, StateFormatError])
def test_optional_reread_failure_does_not_abort_base_restore(
    saved_state, monkeypatch, caplog, failure,
):
    path, _ = saved_state
    real = checkpoint._agent_document
    calls = 0

    def fail_second_read(agent_path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise failure("synthetic extension read failure")
        return real(agent_path)

    monkeypatch.setattr(checkpoint, "_agent_document", fail_second_read)
    agent = _agent()
    previous = agent.intent_memory
    with caplog.at_level(logging.WARNING, logger=checkpoint.__name__):
        assert checkpoint.restore_agent(_metadata(path), agent) is True
    assert calls == 2
    assert agent.hippocampus.experiences == ["synthetic-observation"]
    assert agent.intent_memory is previous
    assert agent.sleep_manager.intent_memory is previous
    assert "IntentMemory extension" in caplog.text


def test_missing_extension_remains_a_quiet_legacy_restore(saved_state, caplog):
    path, _ = saved_state
    agent = _agent()
    previous = agent.intent_memory
    with caplog.at_level(logging.WARNING, logger=checkpoint.__name__):
        assert checkpoint.restore_agent(_metadata(path), agent) is True
    assert agent.intent_memory is previous
    assert agent.sleep_manager.intent_memory is previous
    assert not caplog.records


def test_missing_file_is_contained_by_optional_loader(tmp_path, caplog):
    agent = _agent()
    previous = agent.intent_memory
    with caplog.at_level(logging.WARNING, logger=checkpoint.__name__):
        checkpoint._load_intent_memory_extension(agent, tmp_path / "missing.nowa")
    assert agent.intent_memory is previous
    assert agent.sleep_manager.intent_memory is previous
    assert "IntentMemory extension" in caplog.text


@pytest.mark.parametrize("traces", [[], {}])
def test_valid_empty_list_or_legacy_mapping_restores_both_references(saved_state, traces):
    path, _ = saved_state
    state = _read(path)
    state["sandbox_intent_memory"] = {"traces": traces}
    _write(path, state)
    agent = _agent()
    previous = agent.intent_memory
    assert checkpoint.restore_agent(_metadata(path), agent) is True
    assert agent.intent_memory is not previous
    assert agent.sleep_manager.intent_memory is agent.intent_memory
    assert agent.intent_memory.to_dict()["traces"] == []


@pytest.mark.parametrize("mapping", [False, True])
def test_valid_trace_identity_restores_list_and_legacy_mapping(saved_state, mapping):
    path, _ = saved_state
    row = {"intent_type": "wait", "context_signature": "synthetic-context"}
    state = _read(path)
    state["sandbox_intent_memory"] = {"traces": {"legacy-key": row} if mapping else [row]}
    _write(path, state)
    agent = _agent()
    assert checkpoint.restore_agent(_metadata(path), agent) is True
    assert agent.sleep_manager.intent_memory is agent.intent_memory
    restored = agent.intent_memory.to_dict()["traces"]
    assert len(restored) == 1
    assert restored[0]["intent_type"] == "wait"
    assert restored[0]["context_signature"] == "synthetic-context"


def test_failed_manager_assignment_rolls_back_agent_reference(saved_state, caplog):
    path, _ = saved_state
    state = _read(path)
    state["sandbox_intent_memory"] = {"traces": []}
    _write(path, state)
    agent = _agent()
    previous = agent.intent_memory

    class RejectNewMemory:
        @property
        def intent_memory(self):
            return previous

        @intent_memory.setter
        def intent_memory(self, value):
            if value is not previous:
                raise ValueError("synthetic manager assignment failure")

    agent.sleep_manager = RejectNewMemory()
    with caplog.at_level(logging.WARNING, logger=checkpoint.__name__):
        assert checkpoint.restore_agent(_metadata(path), agent) is True
    assert agent.intent_memory is previous
    assert agent.sleep_manager.intent_memory is previous
    assert "IntentMemory extension" in caplog.text
