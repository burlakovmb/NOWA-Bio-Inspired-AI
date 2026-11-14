"""Regression for issue #10: BG sleep learning must survive decay and normalization."""


import pytest

from learning_guard import learning_allowed


@pytest.fixture(autouse=True)
def _seed_stable_weights_under_sleep_guard():
    """Seed stable weights the way sleep does. Invariant W is test_issue13."""
    with learning_allowed():
        yield


from agent import Agent
from basal_ganglia import ActionChannel
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from selector import ActionSelector
from sleep import CortexMemory, SleepManager
from storage import AgentStorage


def _agent(actions=("act",)):
    hip = NOWAHippocampus(max_experiences=100)
    cortex = CortexMemory()
    intent = IntentMemory()
    sleep = SleepManager(hip, cortex, intent)
    selector = ActionSelector(actions=list(actions))
    agent = Agent(hip, cortex, selector, sleep, intent, rng_seed=0)
    sleep._rng.seed(0)
    return agent


def test_sleep_decay_relaxes_toward_prior_not_zero():
    agent = _agent()
    agent.register_action_channel("act", go_weight=0.4, nogo_weight=0.4, habit_strength=0.2)
    channel = agent.bg_action_channels["act"]
    channel.prior_go = 0.4
    channel.prior_nogo = 0.4
    channel.prior_habit = 0.2
    channel.go_weight = 0.9
    channel.nogo_weight = 0.9
    channel.habit_strength = 0.9
    agent.sleep_manager.decay_rate_sleep = 0.08
    agent.sleep_manager.weight_norm_cap = 10.0

    agent.sleep(cycles=40)

    updated = agent.bg_action_channels["act"]
    assert updated.go_weight > 0.35
    assert updated.nogo_weight > 0.35
    assert updated.habit_strength > 0.20
    assert abs(updated.go_weight - 0.4) < abs(updated.go_weight - 0.0)
    assert abs(updated.habit_strength - 0.2) < abs(updated.habit_strength - 0.0)


def test_normalization_is_per_channel_not_global_l1():
    agent = _agent(actions=("a", "b", "c"))
    for name, go, nogo, habit in (
        ("a", 0.8, 0.5, 0.2),
        ("b", 0.8, 0.5, 0.2),
        ("c", 1.0, 1.0, 1.0),
    ):
        agent.register_action_channel(name, go_weight=go, nogo_weight=nogo, habit_strength=habit)
    sleep = agent.sleep_manager
    sleep.weight_norm_cap = 2.0
    sleep.decay_rate_sleep = 0.0

    applied = sleep._normalize_bg_weights()

    assert applied is True
    assert agent.bg_action_channels["a"].go_weight == pytest.approx(0.8)
    assert agent.bg_action_channels["b"].nogo_weight == pytest.approx(0.5)
    capped = agent.bg_action_channels["c"]
    capped_l1 = abs(capped.go_weight) + abs(capped.nogo_weight) + abs(capped.habit_strength)
    assert capped_l1 == pytest.approx(2.0)
    assert capped.go_weight == pytest.approx(2.0 / 3.0)


def test_repeated_positive_evidence_outruns_decay():
    def _run(with_memory: bool) -> float:
        agent = _agent()
        agent.register_action_channel("act", go_weight=0.55, nogo_weight=0.4, habit_strength=0.1)
        sleep = agent.sleep_manager
        sleep.decay_rate_sleep = 0.02
        sleep.weight_norm_cap = 10.0
        for _ in range(12):
            if with_memory:
                agent.commit_executed_transition(
                    action="act",
                    reward=1.0,
                    context_events=["day"],
                    decided_action="act",
                    terminal=True,
                    dt=0.0,
                )
            agent.sleep(cycles=1)
        return float(agent.bg_action_channels["act"].go_weight)

    evidence = _run(True)
    rested = _run(False)
    assert evidence > 0.55
    assert evidence > rested + 0.05


def test_outcome_cache_is_applied_before_it_is_cleared():
    agent = _agent()
    agent.register_action_channel("act", go_weight=0.5, nogo_weight=0.5, habit_strength=0.1)
    channel = agent.bg_action_channels["act"]
    channel.selection_count = 25
    channel.success_count = 25
    before_go = float(channel.go_weight)
    before_habit = float(channel.habit_strength)
    agent.commit_executed_transition(
        action="act",
        reward=1.0,
        context_events=["ctx"],
        decided_action="act",
        terminal=True,
        dt=0.0,
    )
    agent.sleep_manager.decay_rate_sleep = 0.02
    agent.sleep_manager.weight_norm_cap = 10.0

    agent.sleep(cycles=1)

    updated = agent.bg_action_channels["act"]
    assert updated.go_weight > before_go
    assert updated.habit_strength > before_habit
    assert agent.bg_sleep_memories.get("act", []) == []


def test_old_channel_save_without_priors_adopts_loaded_weights(tmp_path):
    agent = _agent(actions=("act",))
    agent.register_action_channel("act", go_weight=0.62, nogo_weight=0.33, habit_strength=0.17)
    storage = AgentStorage(save_dir=str(tmp_path))
    path = storage.save_agent(
        agent.hippocampus,
        agent.cortex,
        agent.selector,
        sleep_manager=agent.sleep_manager,
        agent=agent,
        filename="bg_priors.pkl",
    )
    from storage import read_agent_state, write_agent_state

    payload = read_agent_state(path)
    channel_blob = payload["bg_action_channels"]["act"]
    for key in ("prior_go", "prior_nogo", "prior_habit"):
        channel_blob.pop(key, None)
    write_agent_state(path, payload)

    restored = _agent(actions=("act",))
    storage.load_agent(
        restored.hippocampus,
        restored.cortex,
        restored.selector,
        path,
        sleep_manager=restored.sleep_manager,
        agent=restored,
    )
    channel = restored.bg_action_channels["act"]
    assert channel.go_weight == pytest.approx(0.62)
    assert channel.nogo_weight == pytest.approx(0.33)
    assert channel.habit_strength == pytest.approx(0.17)
    assert channel.prior_go == pytest.approx(channel.go_weight)
    assert channel.prior_nogo == pytest.approx(channel.nogo_weight)
    assert channel.prior_habit == pytest.approx(channel.habit_strength)


def test_action_channel_prior_defaults_to_initial_weights():
    channel = ActionChannel("act", go_weight=0.2, nogo_weight=0.7, habit_strength=0.15)
    channel.go_weight = 0.9
    assert channel.prior_go == pytest.approx(0.2)
    assert channel.prior_nogo == pytest.approx(0.7)
    assert channel.prior_habit == pytest.approx(0.15)
