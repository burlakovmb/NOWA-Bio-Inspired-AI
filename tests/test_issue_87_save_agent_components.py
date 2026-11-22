"""Issue #87: ``save_agent`` / ``load_agent`` with ``agent=`` alone.

Every optional component the caller does not pass is taken from ``agent=``.
Before the fix only ``value_layer``, ``conflict_arbitration`` and
``intent_memory`` were, so a trained agent lost its temporal chains (held by
the sleep manager), its slow affect and the affect components on a round trip.
An explicitly passed component still wins over the agent's own.
"""

from __future__ import annotations

import json
import random

import pytest

from affective_space import AffectiveSpace
from agent import Agent
from cortex import CortexMemory
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from labile_layer import PlasticityConfig
from learning_guard import stable_payload
from selector import ActionSelector
from sleep import SleepManager
from storage import AgentStorage, read_agent_state

ACTIONS = ("forage", "flee", "hide", "rest")

# save_agent / load_agent keyword -> Agent attribute.
COMPONENTS = (
    ("affect_state", "affect_state"),
    ("temporal", "temporal"),
    ("sleep_manager", "sleep_manager"),
    ("neuromodulators", "neuromodulators"),
    ("affective_persistence", "affective_persistence"),
    ("affective_background", "affective_background"),
    ("affective_space", "affective_space"),
    ("semantic_emotions", "semantic_emotions"),
    ("emotional_memory", "emotional_memory"),
    ("emotional_expectations", "emotional_expectations"),
    ("emotional_regulation", "emotional_regulation"),
    ("emotional_stability", "stability_monitor"),
    ("value_layer", "value_layer"),
    ("conflict_arbitration", "conflict_arbitration"),
    ("intent_memory", "intent_memory"),
)

AFFECT_COMPONENTS = (
    "affect_state",
    "neuromodulators",
    "affective_persistence",
    "affective_background",
    "affective_space",
    "semantic_emotions",
    "emotional_memory",
    "emotional_expectations",
    "emotional_regulation",
    "stability_monitor",
)

# Saved-state keys that only reach the file through a component argument.
SAVED_KEYS = (
    "affect_state",
    "temporal_levels",
    "sleep_manager",
    "neuromodulators",
    "affective_persistence",
    "affective_background",
    "affective_space",
    "semantic_emotions",
    "emotional_memory",
    "emotional_expectations",
    "emotional_regulation",
    "emotional_stability",
    "value_layer",
    "conflict_arbitration",
    "intent_memory",
)


def _build_agent(seed=3):
    hippocampus = NOWAHippocampus(max_experiences=128)
    cortex = CortexMemory()
    memory = IntentMemory()
    sleep_manager = SleepManager(hippocampus, cortex, memory)
    selector = ActionSelector(actions=list(ACTIONS))
    return Agent(
        hippocampus,
        cortex,
        selector,
        sleep_manager,
        memory,
        rng_seed=seed,
        plasticity_config=PlasticityConfig(expected_wake_interval_s=300.0),
    )


def _train(agent, decisions=300, sleep_every=150, seed=4):
    rng = random.Random(seed)
    for index in range(decisions):
        danger = rng.random() < 0.4
        context = ["threat:near" if danger else "threat:none", "food:" + rng.choice(("near", "far"))]
        decided = agent.step(context_events=context, reward=None, decision_only=True, dt=1.5)
        action = decided if decided in ACTIONS else "rest"
        reward = (0.5 if action in ("flee", "hide") else -0.5) if danger else 0.0
        agent.commit_executed_transition(
            action=action,
            reward=reward,
            context_events=context,
            decided_action=decided or None,
            overridden=action != decided,
        )
        if (index + 1) % sleep_every == 0:
            agent.sleep(cycles=2)
    return agent


def _explicit_components(agent):
    return {keyword: getattr(agent, attribute) for keyword, attribute in COMPONENTS}


def _canonical(value):
    return json.dumps(value, default=str, sort_keys=True)


def _component_state(agent, attribute):
    state = getattr(agent, attribute).to_dict()
    if attribute == "emotional_regulation":
        # Inputs of the last regulation call: written each step, read by nothing.
        state = {key: value for key, value in state.items() if key != "last_inputs"}
    return _canonical(state)


def _differing_sections(left, right):
    before = stable_payload(left)
    after = stable_payload(right)
    assert sorted(after) == sorted(before)
    return [name for name in before if _canonical(before[name]) != _canonical(after[name])]


@pytest.fixture(scope="module")
def trained():
    return _train(_build_agent())


@pytest.fixture(scope="module")
def saved(trained, tmp_path_factory):
    directory = tmp_path_factory.mktemp("issue87")
    storage = AgentStorage(save_dir=str(directory))
    short = storage.save_agent(
        trained.hippocampus, trained.cortex, trained.selector, filename="short.nowa", agent=trained
    )
    full = storage.save_agent(
        trained.hippocampus,
        trained.cortex,
        trained.selector,
        filename="full.nowa",
        agent=trained,
        **_explicit_components(trained),
    )
    return storage, short, full


@pytest.fixture(scope="module")
def restored(saved):
    storage, short, _ = saved
    agent = _build_agent()
    storage.load_agent(agent.hippocampus, agent.cortex, agent.selector, short, agent=agent)
    return agent


@pytest.fixture(scope="module")
def restored_explicit(saved):
    storage, _, full = saved
    agent = _build_agent()
    storage.load_agent(
        agent.hippocampus,
        agent.cortex,
        agent.selector,
        full,
        agent=agent,
        **_explicit_components(agent),
    )
    return agent


def test_training_fills_the_sections_the_short_form_used_to_drop(trained):
    payload = stable_payload(trained)
    assert len(payload) == 8
    assert payload["temporal_chains"], "training produced no temporal chains; the round trip would be vacuous"
    assert payload["slow_affect"], "training produced no slow affect; the round trip would be vacuous"


def test_agent_only_save_writes_what_the_explicit_save_writes(saved):
    _, short, full = saved
    short_state = read_agent_state(short)
    full_state = read_agent_state(full)
    assert [key for key in SAVED_KEYS if key not in short_state] == []
    differing = [key for key in SAVED_KEYS if short_state[key] != full_state[key]]
    assert differing == []


def test_agent_only_round_trip_keeps_all_stable_sections(trained, restored):
    assert _differing_sections(trained, restored) == []


def test_agent_only_round_trip_keeps_affect_components(trained, restored):
    # affect_state is reprojected from the affective space on load ("canon
    # wins"), so it is compared with the explicit load below, not with the source.
    differing = [
        attribute
        for attribute in AFFECT_COMPONENTS
        if attribute != "affect_state"
        and _component_state(trained, attribute) != _component_state(restored, attribute)
    ]
    assert differing == []


def test_agent_only_load_matches_explicit_load(restored, restored_explicit):
    assert _differing_sections(restored, restored_explicit) == []
    differing = [
        attribute
        for attribute in AFFECT_COMPONENTS
        if _component_state(restored, attribute) != _component_state(restored_explicit, attribute)
    ]
    assert differing == []


def test_load_keeps_sleep_manager_neuromodulators_shared(restored, restored_explicit):
    assert restored.sleep_manager.neuromodulators is restored.neuromodulators
    assert restored_explicit.sleep_manager.neuromodulators is restored_explicit.neuromodulators


def test_explicit_component_wins_over_agent(trained, tmp_path):
    storage = AgentStorage(save_dir=str(tmp_path))
    explicit = AffectiveSpace()
    explicit.axes["stress"] = 0.75
    path = storage.save_agent(
        trained.hippocampus,
        trained.cortex,
        trained.selector,
        filename="explicit.nowa",
        agent=trained,
        affective_space=explicit,
    )
    assert read_agent_state(path)["affective_space"] == explicit.to_dict()

    agent = _build_agent()
    target = AffectiveSpace()
    untouched = _component_state(agent, "affective_space")
    storage.load_agent(
        agent.hippocampus,
        agent.cortex,
        agent.selector,
        path,
        agent=agent,
        affective_space=target,
    )
    assert target.axes["stress"] == pytest.approx(0.75)
    assert _component_state(agent, "affective_space") == untouched
