"""One TD update per transition, and V(s') comes from the real successor.

Refs #6. A later rating revises the same backup instead of stacking a
second one, and a non-terminal step bootstraps max_a Q(s', a).
"""

from agent import Agent
from cortex import CortexMemory
from experience import Event, EventType
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from selector import ActionSelector
from sleep import SleepManager


def _build_agent(actions):
    hippocampus = NOWAHippocampus(max_experiences=200)
    cortex = CortexMemory()
    intent_memory = IntentMemory()
    sleep_manager = SleepManager(hippocampus, cortex, intent_memory)
    selector = ActionSelector(actions=list(actions))
    return Agent(hippocampus, cortex, selector, sleep_manager, intent_memory)


def _q(agent, context, action) -> float:
    snapshot = agent._build_value_state_snapshot(
        context_events=list(context),
        action=action,
        consequence=None,
        intensity=1.0,
        novelty=0.0,
        conflict=0.0,
    )
    return float(agent.value_layer.get_value(snapshot))


def _effective(agent, context, action) -> float:
    snapshot = agent._build_value_state_snapshot(
        context_events=list(context),
        action=action,
        consequence=None,
        intensity=1.0,
        novelty=0.0,
        conflict=0.0,
    )
    return float(agent.effective_action_value(snapshot, action))


def test_feedback_commits_one_td_update_and_reaches_the_reward():
    """One labile contribution per rating. Stable Q moves only in sleep.

    The old online writer could climb past 0.8 in the same loop. Stable Q
    is replay-only. alpha_sleep is 0.25 * alpha_online, so sleep(cycles=3)
    lands near 0.066 whether the loop is 10 or 80 episodes. > 0.05 fails
    if a cycle of replay is missing (two cycles stay near 0.044).
    """
    agent = _build_agent(["go"])
    before = int(agent.value_layer.online_update_count)
    action = agent.step(["goal"], terminal=True)
    agent.apply_feedback_to_last_experience(2, context_events=["goal"], action_id=action)
    assert int(agent.value_layer.online_update_count) == before
    once = _effective(agent, ["goal"], "go")
    assert once > 0.0

    agent.apply_feedback_to_last_experience(2, context_events=["goal"], action_id=action)
    assert _effective(agent, ["goal"], "go") == once
    assert int(agent.value_layer.online_update_count) == before

    for _ in range(80):
        action = agent.step(["goal"], terminal=True)
        agent.apply_feedback_to_last_experience(2, context_events=["goal"], action_id=action)
    assert _q(agent, ["goal"], "go") == 0.0
    assert _effective(agent, ["goal"], "go") > 0.15
    assert _effective(agent, ["goal"], "go") <= 0.2 + 1e-9
    agent.sleep(cycles=3)
    assert _q(agent, ["goal"], "go") > 0.05


def test_successor_value_is_the_real_next_state():
    agent = _build_agent(["go"])
    successor = ["start", "consequence:arrived"]
    for _ in range(80):
        action = agent.step(successor, terminal=True)
        agent.apply_feedback_to_last_experience(
            2,
            context_events=successor,
            action_id=action,
        )
    agent.sleep(cycles=3)
    assert _q(agent, successor, "go") > 0.05

    # Reward 0 on the way into a valuable successor must not stay at 0.
    # The waking backup is labile and uses max_a Q_eff(s', a). Stable Q(s)
    # stays 0 until a later sleep; this test's claim is the successor term.
    for _ in range(80):
        action = agent.step(
            ["start"],
            consequence=Event("arrived", event_type=EventType.CONSEQUENCE),
            reward=0.0,
            terminal=False,
        )
    learned = _effective(agent, ["start"], action)
    assert _q(agent, ["start"], action) == 0.0
    cold = _build_agent(["go"])
    cold.step(
        ["start"],
        consequence=Event("arrived", event_type=EventType.CONSEQUENCE),
        reward=0.0,
        terminal=False,
    )
    assert learned > _effective(cold, ["start"], "go")
    # Reward is 0, so the replay salience/TD filters do not write stable Q.
    # The labile step is 0.1·α, so this cannot reach the old waking Q > 0.4.
    # It must still beat a cold agent and clear a non-zero bootstrap.
    assert learned > 0.01
