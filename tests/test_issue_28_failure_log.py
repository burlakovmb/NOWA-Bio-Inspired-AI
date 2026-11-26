"""Issue #28: the autonomous runtime's failure_log keeps a bounded tail.

``_record_failure`` used to append for the whole life of the runtime. It now keeps the latest
``FAILURE_LOG_RETAIN`` entries, and a save that holds more is trimmed to that tail on restore.
"""

from __future__ import annotations

import pytest

from agent import Agent
from autonomous_organism import FAILURE_LOG_RETAIN
from cortex import CortexMemory
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from selector import ActionSelector
from sleep import SleepManager


def _agent():
    hippocampus = NOWAHippocampus()
    cortex = CortexMemory()
    memory = IntentMemory()
    return Agent(hippocampus, cortex, ActionSelector(actions=["a", "b"]), SleepManager(hippocampus, cortex, memory),
                 memory)


def _runtime(agent):
    runtime = agent.init_autonomous_runtime()
    if runtime is None:
        pytest.skip("autonomous runtime unavailable in current environment")
    return runtime


def test_failure_log_keeps_the_latest_tail():
    runtime = _runtime(_agent())
    runtime.failure_log.clear()
    total = FAILURE_LOG_RETAIN + 44
    for index in range(total):
        runtime._record_failure("test", {"n": index})
    assert len(runtime.failure_log) == FAILURE_LOG_RETAIN
    assert runtime.failure_log[0]["details"]["n"] == total - FAILURE_LOG_RETAIN
    assert runtime.failure_log[-1]["details"]["n"] == total - 1


def test_a_short_log_is_kept_whole():
    runtime = _runtime(_agent())
    runtime.failure_log.clear()
    for index in range(3):
        runtime._record_failure("test", {"n": index})
    assert [entry["details"]["n"] for entry in runtime.failure_log] == [0, 1, 2]


def test_restore_trims_an_oversized_saved_log():
    agent = _agent()
    runtime = _runtime(agent)
    state = agent.get_autonomous_state()
    state["failures"] = [{"timestamp": float(i), "failure_mode": "old", "details": {"n": i}}
                         for i in range(FAILURE_LOG_RETAIN + 10)]
    restored = _agent()
    _runtime(restored)
    assert restored.restore_autonomous_state(state)
    log = restored.autonomous_runtime.failure_log
    assert len(log) == FAILURE_LOG_RETAIN
    assert log[-1]["details"]["n"] == FAILURE_LOG_RETAIN + 9
