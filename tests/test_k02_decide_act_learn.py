"""K02: the episode must learn the executed action and the outcome reward.

The colony used to score reward, including valence, and store the cognitive
choice before reflexes and the homeostatic gate ran. These checks fail on
that order. They do not use PYTHONHASHSEED.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from agent import Agent
from cortex import CortexMemory
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from selector import ActionSelector
from sleep import SleepManager

COLONY_SRC = Path(__file__).resolve().parents[1] / "Demo" / "Colony chinchillas" / "src"
if str(COLONY_SRC) not in sys.path:
    sys.path.insert(0, str(COLONY_SRC))

from colony_agent import ChinchillaAgent  # noqa: E402
from shared_resources import SharedResources  # noqa: E402


def _core_agent() -> Agent:
    hippocampus = NOWAHippocampus(max_experiences=32)
    cortex = CortexMemory()
    memory = IntentMemory()
    sleep_manager = SleepManager(hippocampus, cortex, memory)
    selector = ActionSelector(actions=["rest", "eat", "hide"])
    return Agent(
        hippocampus,
        cortex,
        selector,
        sleep_manager,
        memory,
        rng_seed=20,
    )


def _episode_action(exp) -> str:
    replay = str(getattr(exp, "replay_action_id", "") or "")
    if replay:
        return replay
    for event in getattr(getattr(exp, "path", None), "events", ()) or ():
        name = str(getattr(event, "name", ""))
        if name.startswith("action:"):
            return name.split(":", 1)[1]
    return ""


def test_commit_stores_executed_action_and_override_flag():
    agent = _core_agent()
    context = ["zone:floor", "hunger_critical"]
    decided = agent.step(context, decision_only=True, reward=None)
    assert decided
    before = len(agent.hippocampus.experiences)
    episode_id = agent.commit_executed_transition(
        action="eat",
        reward=0.5,
        context_events=context,
        decided_action=decided,
        overridden=True,
        override_source="homeostatic:critical_hunger",
        intensity=1.0,
    )
    assert episode_id
    assert len(agent.hippocampus.experiences) == before + 1
    exp = agent.hippocampus.get_experience(episode_id)
    assert exp is not None
    assert _episode_action(exp) == "eat"
    assert bool(getattr(exp, "overridden", False)) is True
    assert getattr(exp, "override_source", None) == "homeostatic:critical_hunger"
    assert getattr(exp, "decided_action", None) == decided
    assert abs(float(exp.reward) - 0.5) < 1e-9

    signature = agent.intent_memory._compute_context_signature(context)
    trace = agent.intent_memory.traces.get(f"eat:{signature}")
    assert trace is not None
    strength = float(trace.strength)
    repeated = agent.apply_feedback_to_last_experience(
        1,
        context_events=context,
        action_id="eat",
        episode_id=episode_id,
    )
    assert repeated["updated"] is True
    again = agent.apply_feedback_to_last_experience(
        1,
        context_events=context,
        action_id="eat",
        episode_id=episode_id,
    )
    assert again["updated"] is True
    assert float(trace.strength) == pytest.approx(strength)


def test_colony_episode_follows_executed_outcome_not_pre_action_choice():
    agent = ChinchillaAgent(sex="F", physiology_as_policy=False)
    agent.colony = []
    agent.resources = SharedResources(food_pellets=1.0, hay=1.0, water=1.0)
    agent.position = "bowl_pellets"
    agent.hunger = 0.9
    agent.thirst = 0.1
    agent.wakefulness.wakefulness = 0.1
    agent.affective_space.axes["valence"] = 1.0
    agent.affective_space.axes["stress"] = 0.0

    with patch.object(Agent, "step", return_value="play"):
        agent.sim_step(0.1)
        spent = 0.0
        while not agent.hippocampus.experiences and spent < 120.0:
            agent.sim_step(0.1)
            spent += 0.1

    assert agent.hunger < 0.9
    assert agent.hippocampus.experiences, "the eat bout did not commit"
    exp = agent.hippocampus.experiences[-1]
    assert _episode_action(exp) == "eat"
    assert bool(getattr(exp, "overridden", False)) is True
    assert str(getattr(exp, "override_source", "")).startswith("homeostatic:")
    assert getattr(exp, "decided_action", None) == "play"
    # Post-eat relief is the outcome. The pre-action score of this state,
    # including +0.3 valence, stays below the relief credit.
    assert float(exp.reward) > 0.35


def test_reward_does_not_add_valence():
    agent = ChinchillaAgent(sex="M")
    agent.resources = SharedResources(food_pellets=1.0, hay=1.0, water=1.0)
    agent.hunger = 0.2
    agent.thirst = 0.2
    agent.affective_space.axes["stress"] = 0.0
    agent.affective_space.axes["valence"] = 0.0
    neutral = agent._compute_reward()
    agent.affective_space.axes["valence"] = 1.0
    elevated = agent._compute_reward()
    assert elevated == pytest.approx(neutral)
    assert elevated < 0.35
