"""Issue #86: temporal chains and stable visit counts have a finite capacity with forgetting.

At the end of each night (``SleepManager.deep_sleep``) chains that stayed weak and were not formed again for
``stale_sleeps`` nights are pruned, a hard capacity evicts the weakest and least recent beyond it, and the stable
visit counts of contexts not visited for ``visit_halving_sleeps`` nights are halved, with the table capped at
``visit_capacity`` rows. Recency is counted in nights, not wall-clock seconds.
"""

from __future__ import annotations

import random

from agent import Agent
from cortex import CortexMemory
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from labile_layer import PlasticityConfig
from selector import ActionSelector
from sleep import SleepManager
from storage import AgentStorage
from temporal_chains import ChainMemory

ACTIONS = tuple(f"a{k}" for k in range(4))


def _close(memory, nights):
    for _ in range(nights):
        memory.close_night()


def test_weak_chain_is_pruned_after_stale_nights():
    memory = ChainMemory(min_support=6, stale_sleeps=3)
    memory.add_or_update(("e1", "action:a0"), 0.2)
    _close(memory, 3)
    assert ("e1", "action:a0") in memory.chains          # not reconfirmed for 2 nights: kept
    _close(memory, 1)
    assert ("e1", "action:a0") not in memory.chains      # 3 nights without reconfirmation: pruned


def test_reconfirmed_chain_survives():
    memory = ChainMemory(min_support=6, stale_sleeps=3)
    for _ in range(10):
        memory.add_or_update(("e1", "action:a0"), 0.2)   # formed again every night
        memory.close_night()
    assert ("e1", "action:a0") in memory.chains


def test_strong_chain_survives_staleness():
    memory = ChainMemory(min_support=3, stale_sleeps=2)
    for _ in range(3):
        memory.add_or_update(("e1", "action:a0"), 0.2)   # support 3 in one night
    _close(memory, 10)
    assert ("e1", "action:a0") in memory.chains          # well supported: staleness alone does not prune it


def test_capacity_evicts_the_weakest_and_least_recent():
    memory = ChainMemory(capacity=3, min_support=1, stale_sleeps=100)
    for support, name in enumerate(("e0", "e1", "e2", "e3", "e4"), start=1):
        for _ in range(support):
            memory.add_or_update((name, "action:a0"), 0.1)
    stats = memory.close_night()
    assert stats["chains_evicted"] == 2
    assert sorted(key[0] for key in memory.chains) == ["e2", "e3", "e4"]


def test_round_trip_keeps_night_stamps_and_old_saves_are_not_pruned():
    memory = ChainMemory(min_support=6, stale_sleeps=3)
    memory.add_or_update(("e1", "action:a0"), 0.2)
    _close(memory, 2)
    data = memory.to_dict()
    restored = ChainMemory(min_support=6, stale_sleeps=3)
    restored.from_dict(data)
    assert restored.sleep_index == 2
    assert restored.chains[("e1", "action:a0")].last_seen_sleep == 0

    old = {"chains": {("e9", "action:a1"): {"signature": ["e9", "action:a1"], "net_affect": 0.1,
                                             "stability": 0.0, "usage_count": 1}}}
    legacy = ChainMemory(min_support=6, stale_sleeps=3)
    legacy.sleep_index = 5
    legacy.from_dict(old)                                # a save made before issue #86
    legacy.close_night()
    assert ("e9", "action:a1") in legacy.chains          # counted as seen now, not stale


class _Host:
    def __init__(self, counts):
        self._action_visit_counts = counts


def _manager_with_counts(counts, night, halving=4, capacity=0, last_visit=None):
    manager = SleepManager(NOWAHippocampus(max_experiences=8), CortexMemory(), IntentMemory())
    manager._host_agent = _Host(counts)
    manager.chain_memory.sleep_index = night
    manager.visit_halving_sleeps = halving
    manager.visit_capacity = capacity
    manager._visit_context_night = dict(last_visit or {})
    return manager


def test_stale_visit_counts_halve_on_schedule_and_drop_at_zero():
    counts = {("old", "a0"): 9, ("old", "a1"): 1}
    _manager_with_counts(counts, night=6, halving=4, last_visit={"old": 0})._close_night()
    assert counts == {("old", "a0"): 9, ("old", "a1"): 1}   # night 7: not a halving night
    _manager_with_counts(counts, night=7, halving=4, last_visit={"old": 0})._close_night()
    assert counts == {("old", "a0"): 4}                     # night 8: halved, a single visit is forgotten


def test_visit_counts_of_a_context_in_use_do_not_fade():
    counts = {("used", "a0"): 9, ("used", "a1"): 1, ("old", "a0"): 9}
    _manager_with_counts(counts, night=7, halving=4, last_visit={"used": 6, "old": 1})._close_night()
    assert counts == {("used", "a0"): 9, ("used", "a1"): 1, ("old", "a0"): 4}


def test_visit_counts_capped_by_smallest_count():
    counts = {("c1", "a0"): 5, ("c2", "a0"): 1, ("c3", "a0"): 3, ("c4", "a0"): 2}
    stats = _manager_with_counts(counts, night=0, halving=0, capacity=2)._close_night()
    assert counts == {("c1", "a0"): 5, ("c3", "a0"): 3}
    assert stats["visit_rows_dropped"] == 2


def _agent(seed=5):
    hippocampus = NOWAHippocampus(max_experiences=128)
    cortex = CortexMemory()
    memory = IntentMemory()
    manager = SleepManager(hippocampus, cortex, memory)
    selector = ActionSelector(actions=list(ACTIONS))
    return Agent(hippocampus, cortex, selector, manager, memory, rng_seed=seed,
                 plasticity_config=PlasticityConfig(expected_wake_interval_s=300.0))


def test_a_diverse_life_stays_within_the_chain_capacity(tmp_path):
    random.seed(5)
    agent = _agent()
    agent.sleep_manager.chain_memory.capacity = 60
    rng = random.Random(6)
    nights = 0
    for index in range(600):
        context = [f"f{k}:" + rng.choice(("lo", "mid", "hi")) for k in range(4)]
        decided = agent.step(context_events=context, reward=None, decision_only=True, dt=1.5)
        action = decided if decided in ACTIONS else ACTIONS[0]
        agent.commit_executed_transition(action=action, reward=0.3 if action == ACTIONS[1] else -0.1,
                                         context_events=context)
        if (index + 1) % 100 == 0:
            agent.sleep(cycles=3)                        # strict learning (conftest): writes only in sleep
            nights += 1
            assert len(agent.sleep_manager.chain_memory.chains) <= 60
    assert agent.sleep_manager.chain_memory.sleep_index == nights

    storage = AgentStorage(save_dir=str(tmp_path))
    path = storage.save_agent(agent.hippocampus, agent.cortex, agent.selector, filename="a.nowa", agent=agent)
    restored = _agent()
    storage.load_agent(restored.hippocampus, restored.cortex, restored.selector, str(path), agent=restored)
    assert restored.sleep_manager.chain_memory.sleep_index == nights
