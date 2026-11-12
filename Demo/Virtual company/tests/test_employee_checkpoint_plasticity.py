"""Employee checkpoints keep sleep consolidation on the restored labile tier.

``AgentStorage.load_agent`` rebinds the sleep manager to the restored
``labile`` and ``plasticity``. These tests remain the regression for that
contract: a pending tag, capture parameters, and a file that predates
``vc_intent_memory``.
"""

from __future__ import annotations

import pytest

from nowa_body.employee_checkpoint import load_mind, save_mind
from nowa_body.employee_session import spawn_employee_agent
from nowa_body.feedback_loop import store_lesson

CONTEXT = ["event:stock_critical_low"]
ACTION = "wait_and_monitor"
KAPPA = 0.9
ETA_SLEEP = 0.12
ETA_LABILE = 0.04
WAKE_S = 7200.0


@pytest.fixture(autouse=True)
def strict_mode_with_swallow_trap(monkeypatch):
    """Strict mode. A ``WakingLearningError`` that is raised and caught fails the test."""
    monkeypatch.setenv("NOWA_STRICT_LEARNING", "1")
    import learning_guard

    raised: list = []
    original = learning_guard.WakingLearningError

    class _Counting(original):
        def __init__(self, *args):
            raised.append(" ".join(str(item) for item in args))
            super().__init__(*args)

    monkeypatch.setattr(learning_guard, "WakingLearningError", _Counting)
    yield
    if raised:
        pytest.fail("WakingLearningError was raised and caught: " + " | ".join(raised))


def _custom_plasticity(agent) -> None:
    plasticity = agent.plasticity
    plasticity.expected_wake_interval_s = WAKE_S
    plasticity.capture_kappa = KAPPA
    plasticity.eta_channel_sleep = ETA_SLEEP
    plasticity.eta_labile_channel = ETA_LABILE


def _agent_with_pending_lesson():
    agent = spawn_employee_agent("buyer")
    if getattr(agent, "labile", None) is None:
        pytest.skip("core Agent unavailable; lab stub has no two-tier layer")
    _custom_plasticity(agent)
    stored = store_lesson(agent, CONTEXT, ACTION, 0.8, consequence="lesson")
    assert stored is not None
    assert len(agent.labile._contributions) == 1
    return agent, stored


def _weights(agent):
    channel = agent.bg_action_channels[ACTION]
    return channel.go_weight, channel.nogo_weight


def _fresh_loaded(tmp_path, source):
    path = tmp_path / "mind.pkl"
    save_mind(source, path)
    restored = spawn_employee_agent("buyer")
    load_mind(restored, path)
    return restored


def test_manager_is_rebound_to_restored_objects(tmp_path):
    source, _ = _agent_with_pending_lesson()
    restored = _fresh_loaded(tmp_path, source)

    manager = restored.sleep_manager
    assert manager.labile is restored.labile
    assert manager.plasticity is restored.plasticity
    assert restored.labile.config is restored.plasticity
    assert restored.plasticity.capture_kappa == KAPPA
    assert restored.plasticity.eta_channel_sleep == ETA_SLEEP
    assert restored.plasticity.eta_labile_channel == ETA_LABILE
    assert restored.plasticity.expected_wake_interval_s == WAKE_S
    assert len(restored.labile._contributions) == 1
    assert manager._host_agent is restored


def test_load_lesson_sleep_captures_pending_tag_once_with_restored_parameters(tmp_path):
    source, _ = _agent_with_pending_lesson()
    restored = _fresh_loaded(tmp_path, source)

    episode_id = next(iter(restored.labile._contributions))
    now = restored._host_clock_s
    go_tag, nogo_tag = restored.labile.remaining_channel(episode_id, now)
    assert go_tag > 0.0
    go0, nogo0 = _weights(restored)
    reward = 0.8
    eta_eff = ETA_SLEEP - KAPPA * ETA_LABILE
    expected_go = go0 + KAPPA * go_tag + eta_eff * reward
    expected_nogo = nogo0 + KAPPA * nogo_tag - 0.5 * eta_eff * reward

    manager = restored.sleep_manager
    exp = restored.hippocampus.get_experience(episode_id)
    from learning_guard import learning_allowed

    with learning_allowed():
        manager._apply_episode_channel_and_habit(exp)

    go1, nogo1 = _weights(restored)
    assert go1 == pytest.approx(expected_go, abs=1e-9)
    assert nogo1 == pytest.approx(expected_nogo, abs=1e-9)
    # The tag is consumed on the layer the agent actually owns: exactly once.
    assert episode_id not in restored.labile._contributions
    assert restored.labile._contributions == {}


def test_agent_sleep_after_load_matches_in_process_sleep(tmp_path):
    source, _ = _agent_with_pending_lesson()
    restored = _fresh_loaded(tmp_path, source)
    episode_id = next(iter(restored.labile._contributions))

    restored_result = restored.sleep(cycles=1)
    source.sleep(cycles=1)

    assert not restored_result.get("error")
    assert restored.labile._contributions == {}
    assert restored.hippocampus.get_experience(episode_id).consolidated is True
    assert source.labile._contributions == {}
    assert _weights(restored) == pytest.approx(_weights(source), abs=1e-9)


def test_old_file_without_intent_memory_keeps_restored_labile(tmp_path):
    source, _ = _agent_with_pending_lesson()
    path = tmp_path / "mind.pkl"
    save_mind(source, path)

    import pickle

    with path.open("rb") as stream:
        state = pickle.load(stream)
    state.pop("vc_intent_memory", None)
    with path.open("wb") as stream:
        pickle.dump(state, stream)

    restored = spawn_employee_agent("buyer")
    load_mind(restored, path)
    assert restored.sleep_manager.labile is restored.labile
    assert restored.sleep_manager.plasticity is restored.plasticity
