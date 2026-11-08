"""Real-core lesson persistence and rejection of unauditable training input."""
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys

import pytest

from nowa_body.onboarding import evaluate, make_runtime, practice, train, validate_lessons
from nowa_body.employee_checkpoint import load_mind, save_mind

ROLE = Path(__file__).resolve().parents[1] / "src/nowa_roles/procurement/config.yaml"
WAIT = "wait_and_monitor"


def lesson():
    return {"id": "budget-unknown", "context_tokens": ["event:budget_unknown", "domain:finance"],
            "action": WAIT, "reward": 0.6, "consequence": "await_budget_confirmation",
            "provenance": {"source": "agreed_unknown_budget_rule"}}


@pytest.mark.parametrize("field,value", [
    ("provenance", {}), ("reward", float("nan")), ("reward", 2),
    ("action", "unregistered_action"), ("context_tokens", ["action:forced_answer"]),
])
def test_rejects_unauditable_or_invalid_lesson(field, value):
    row = lesson()
    row[field] = value
    with pytest.raises(ValueError):
        validate_lessons({"lessons": [row]}, {WAIT})


def test_existing_employee_cannot_be_overwritten(tmp_path):
    target = tmp_path / "existing_buyer"
    target.mkdir()
    checkpoint = target / "mind.pkl"
    checkpoint.write_bytes(b"existing checkpoint")
    with pytest.raises(FileExistsError):
        train(target, ROLE, tmp_path / "not-needed.json")
    assert checkpoint.read_bytes() == b"existing checkpoint"


def test_old_practice_cannot_replay_a_superseded_phase_corpus(tmp_path):
    training = tmp_path / "phase_buyer/training"
    training.mkdir(parents=True)
    (training / "training-result.json").write_text(
        json.dumps({"active_phase": "retrospective-20261104"}), encoding="utf-8")
    with pytest.raises(ValueError, match="active phase corpus"):
        practice(training.parent, cycles=1)


def test_cli_guard_blocks_real_socket_before_connect():
    script = '''
import socket, sys
from nowa_body.onboarding import offline_audit
sys.addaudithook(offline_audit)
try:
    socket.socket().connect(("127.0.0.1", 9))
except RuntimeError as error:
    assert "offline onboarding forbids socket.connect" in str(error)
    print("blocked before connection")
else:
    raise AssertionError("network guard failed")
'''
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROLE.parents[2])
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "blocked before connection" in result.stdout


def test_legacy_mind_without_intent_extension_still_loads(tmp_path):
    agent, _, _ = make_runtime(ROLE, "legacy_buyer", 1)
    path = tmp_path / "legacy.pkl"
    save_mind(agent, path)
    with path.open("rb") as stream:
        state = pickle.load(stream)
    state.pop("vc_intent_memory")
    with path.open("wb") as stream:
        pickle.dump(state, stream)
    restored, _, _ = make_runtime(ROLE, "legacy_buyer", 1)
    load_mind(restored, path)
    assert restored.selector.actions == agent.selector.actions
    assert len(restored.hippocampus.experiences) == len(agent.hippocampus.experiences)


def test_real_core_sleep_checkpoint_and_reload(tmp_path, monkeypatch):
    monkeypatch.setenv("NOWA_STRICT_LEARNING", "1")
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps({"lessons": [lesson()]}), encoding="utf-8")
    target = tmp_path / "test_buyer"
    trained = train(target, ROLE, corpus)
    assert trained["waking_stable_unchanged"]
    assert trained["sleep_changed_stable"]
    assert trained["consolidated_lessons"] == 1
    assert (target / "training/checkpoints/cycle-001.pkl").is_file()
    events = [json.loads(line) for line in (target / "training/lessons.jsonl").read_text().splitlines()]
    assert [e["event"] for e in events] == ["baseline", "lesson", "checkpoint"]
    probes = tmp_path / "probes.json"
    probes.write_text(json.dumps({"probes": [{"id": "retention", "group": "trained_context",
                        "context_tokens": lesson()["context_tokens"], "expected_action": WAIT}]}), encoding="utf-8")
    result = evaluate(target, probes)
    assert result["restored_stable_exactly"], result["mismatched_stable_components"]
    assert result["mind_file_unchanged"]
    assert all(row["stable_unchanged"] for row in result["rows"])
    assert result["rows"] == evaluate(target, probes)["rows"]
    assert result["deployment_ready"] is False
    practiced = practice(target, cycles=1)
    assert practiced["completed_cycles"] == 2
    assert practiced["lessons"] == practiced["consolidated_lessons"] == 2
    assert (target / "training/checkpoints/cycle-001.pkl").is_file()
    assert (target / "training/checkpoints/cycle-002.pkl").is_file()
    assert (target / "training/evaluation-cycle-001.json").is_file()
    assert evaluate(target, probes)["restored_stable_exactly"]
