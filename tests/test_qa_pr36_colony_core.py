"""Independent QA for PR #36 (issues #19, #20, #21).

These checks rebuild the contracts instead of calling the senior tests:
decide then act then learn, a canonical habit key, and colony survival
that depends on the core only when PHYSIOLOGY_AS_POLICY is on.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

import pytest

from agent import Agent
from cortex import CortexMemory
from data_loader import load_habits_from_dataset
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from selector import ActionSelector
from sleep import SleepManager
from storage import AgentStorage

COLONY_SRC = Path(__file__).resolve().parents[1] / "Demo" / "Colony chinchillas" / "src"
if str(COLONY_SRC) not in sys.path:
    sys.path.insert(0, str(COLONY_SRC))

from agent_knowledge import KnownAgent  # noqa: E402
from colony_agent import ChinchillaAgent  # noqa: E402
from colony_storage import ColonyStorage  # noqa: E402
from config_colony import (  # noqa: E402
    ESTRUS_DURATION_S,
    HEAT_CYCLE_LENGTH_S,
    MATURITY_AGE_S,
    PHYSIOLOGY_AS_POLICY,
)
from shared_resources import SharedResources  # noqa: E402
from simulation_runner import SimulationRunner  # noqa: E402

_NAME = re.compile(r"^G[0-9]+A[0-9]+S[MFU]$")


def _core(actions=("rest", "eat", "hide", "play")) -> Agent:
    hippocampus = NOWAHippocampus(max_experiences=40)
    cortex = CortexMemory()
    memory = IntentMemory()
    sleep_manager = SleepManager(hippocampus, cortex, memory)
    selector = ActionSelector(actions=list(actions))
    agent = Agent(hippocampus, cortex, selector, sleep_manager, memory, rng_seed=36)
    for name in actions:
        agent.register_action_channel(name, go_weight=0.5, nogo_weight=0.4, habit_strength=0.1)
    return agent


def _weights(agent: Agent, action: str) -> tuple[float, float, float, int]:
    channel = agent.bg_action_channels[action]
    go, nogo = agent.labile.effective_channel(
        action,
        float(channel.go_weight),
        float(channel.nogo_weight),
        float(getattr(agent, "_host_clock_s", 0.0)),
    )
    habit = 0.0
    signature = agent.intent_memory._compute_context_signature(
        list(getattr(agent, "_qa_context", []) or [])
    )
    trace = agent.intent_memory.traces.get(f"{action}:{signature}")
    if trace is not None:
        habit = float(trace.strength)
    return (
        float(go),
        float(nogo),
        habit,
        len(agent.bg_sleep_memories.get(action, [])),
    )


def test_decision_only_does_not_store_or_learn():
    agent = _core()
    context = ["zone:floor", "hunger_high"]
    before_q = agent.value_layer.get_value(
        agent._build_value_state_snapshot(context, "eat", None, 1.0, 0.0, 0.0)
    )
    episodes = len(agent.hippocampus.experiences)
    decided = agent.step(context, reward=1.0, decision_only=True, intensity=1.0)
    assert decided in {"rest", "eat", "hide", "play", "NO_ACTION"}
    assert len(agent.hippocampus.experiences) == episodes
    assert agent.bg_sleep_memories == {}
    assert agent.bg_action_channels["eat"].go_weight == pytest.approx(0.5)
    after_q = agent.value_layer.get_value(
        agent._build_value_state_snapshot(context, "eat", None, 1.0, 0.0, 0.0)
    )
    assert after_q == pytest.approx(before_q)


def test_commit_credits_executed_action_and_repeated_feedback_is_a_noop():
    agent = _core()
    context = ["zone:floor", "hunger_critical", "food_ok"]
    agent._qa_context = context
    decided = agent.step(context, decision_only=True, reward=None)
    episode_id = agent.commit_executed_transition(
        action="eat",
        reward=1.0,
        context_events=context,
        decided_action=decided,
        overridden=True,
        override_source="reflex:urgent_feed",
    )
    exp = agent.hippocampus.get_experience(episode_id)
    assert exp is not None
    assert exp.replay_action_id == "eat"
    assert exp.overridden is True
    assert exp.override_source == "reflex:urgent_feed"
    assert exp.decided_action == decided
    assert float(exp.reward) == pytest.approx(1.0)
    eat_go, _eat_nogo = agent.labile.effective_channel(
        "eat",
        agent.bg_action_channels["eat"].go_weight,
        agent.bg_action_channels["eat"].nogo_weight,
        agent._host_clock_s,
    )
    assert eat_go > 0.5
    assert agent.bg_action_channels["eat"].go_weight == pytest.approx(0.5)
    assert agent.bg_action_channels[decided].go_weight == pytest.approx(0.5) or decided == "eat"

    frozen = _weights(agent, "eat")
    first = agent.apply_feedback_to_last_experience(2, context, "eat", episode_id)
    second = agent.apply_feedback_to_last_experience(2, context, "eat", episode_id)
    assert first["updated"] is True
    assert second["updated"] is True
    assert _weights(agent, "eat") == pytest.approx(frozen)

    # A changed rating may revise Q. The same revised rating must not apply twice.
    revised = agent.apply_feedback_to_last_experience(-2, context, "eat", episode_id)
    assert revised["updated"] is True
    after_revision = _weights(agent, "eat")
    assert after_revision != pytest.approx(frozen)
    again = agent.apply_feedback_to_last_experience(-2, context, "eat", episode_id)
    assert _weights(agent, "eat") == pytest.approx(after_revision)
    other = agent.step(["zone:shelf"], decision_only=True)
    other_id = agent.commit_executed_transition(
        action="hide",
        reward=0.0,
        context_events=["zone:shelf"],
        decided_action=other,
        overridden=False,
    )
    untouched = agent.hippocampus.get_experience(episode_id)
    assert float(untouched.reward) == pytest.approx(-1.0)
    assert agent.hippocampus.get_experience(other_id).replay_action_id == "hide"


def test_colony_override_credits_hide_not_the_rest_choice():
    agent = ChinchillaAgent(sex="F", name="Luna", rng_seed=4, physiology_as_policy=True)
    agent.replaced_policy_action = "rest"
    agent.colony = [agent]
    agent.resources = SharedResources()
    agent.affective_space.axes["stress"] = 0.95
    agent.hunger = 0.2
    agent.thirst = 0.2
    agent.wakefulness.wakefulness = 0.1
    agent.register_action_channel("rest", go_weight=0.5, nogo_weight=0.4, habit_strength=0.0)
    agent.register_action_channel("hide", go_weight=0.5, nogo_weight=0.4, habit_strength=0.0)
    agent.sim_step(0.1)
    assert agent.current_action == "hide"
    exp = agent.hippocampus.experiences[-1]
    assert exp.replay_action_id == "hide"
    assert exp.decided_action == "rest"
    assert str(exp.override_source).startswith("reflex:")
    # Stable Go stays put while awake. A non-zero outcome credits hide on the labile tag.
    assert agent.bg_action_channels["hide"].go_weight == pytest.approx(
        agent.bg_action_channels["rest"].go_weight
    )
    reward = float(getattr(exp, "td_committed_reward", 0.0) or 0.0)
    if abs(reward) > 1e-9:
        now = float(agent._host_clock_s)
        hide_go, _hide_nogo = agent.labile.channel_offset("hide", now)
        rest_go, _rest_nogo = agent.labile.channel_offset("rest", now)
        assert hide_go != pytest.approx(rest_go)


def test_reward_ignores_valence_and_is_scored_after_the_action():
    agent = ChinchillaAgent(sex="M", name="Milo", rng_seed=5)
    agent.resources = SharedResources(food_pellets=1.0, hay=1.0, water=1.0)
    agent.hunger = 0.2
    agent.thirst = 0.2
    agent.affective_space.axes["stress"] = 0.0
    agent.affective_space.axes["valence"] = -1.0
    low = agent._compute_reward()
    agent.affective_space.axes["valence"] = 1.0
    high = agent._compute_reward()
    assert high == pytest.approx(low)

    fed = ChinchillaAgent(sex="F", name="Luna", rng_seed=6, physiology_as_policy=False)
    fed.replaced_policy_action = "rest"
    fed.colony = [fed]
    fed.resources = SharedResources()
    assert fed.resources.food_pellets > 0.05
    assert fed.resources.hay > 0.05
    fed.position = "bowl_pellets"
    fed.hunger = 0.9
    fed.thirst = 0.1
    fed.wakefulness.wakefulness = 0.1
    fed.affective_space.axes["valence"] = 1.0
    before = fed.hunger
    fed.sim_step(0.1)
    assert fed.current_action == "eat"
    assert fed.hunger < before
    exp = fed.hippocampus.experiences[-1]
    assert exp.replay_action_id == "eat"
    assert exp.decided_action == "rest"
    assert bool(exp.overridden) is True


def test_habit_key_is_a_canonical_set_and_old_files_still_load():
    memory = IntentMemory()
    hungry = ["zone:floor", "food_ok", "hunger_high"]
    alarmed = ["zone:floor", "alarm_call", "hunger_high"]
    assert memory._compute_context_signature(hungry) != memory._compute_context_signature(alarmed)
    assert hashlib.md5(b"hunger_high").hexdigest()[:8] == hashlib.md5(hungry[-1].encode()).hexdigest()[:8]

    ordered = ["alarm_call", "zone:wheel", "hunger_high", "food_ok"]
    shuffled = ["food_ok", "hunger_high", "alarm_call", "zone:wheel"]
    duplicated = ["hunger_high", " food_ok ", "hunger_high", "", "alarm_call", "zone:wheel"]
    assert memory._compute_context_signature(ordered) == memory._compute_context_signature(shuffled)
    # Blank tokens drop out. A spaced token is not the same event as food_ok,
    # so the duplicate case below uses exact copies.
    copies = ["hunger_high", "food_ok", "hunger_high", "alarm_call", "zone:wheel"]
    assert memory._compute_context_signature(copies) == memory._compute_context_signature(ordered)
    assert memory._compute_context_signature([]) == memory._compute_context_signature(["", "  "])
    assert memory._compute_context_signature(["hunger_high"]) == hashlib.md5(b"hunger_high").hexdigest()[:8]

    from learning_guard import learning_allowed

    with learning_allowed():
        for _ in range(25):
            memory.apply_outcome(hungry, "eat", 1.0)
            memory.apply_outcome(alarmed, "hide", 1.0)
    hungry_key = memory._compute_context_signature(hungry)
    alarmed_key = memory._compute_context_signature(alarmed)
    assert memory.traces[f"eat:{hungry_key}"].strength > 0.9
    assert memory.traces[f"hide:{alarmed_key}"].strength > 0.9
    assert memory.activate_by_context(hungry).get("hide", 0.0) == 0.0
    assert memory.activate_by_context(alarmed).get("eat", 0.0) == 0.0

    habits = load_habits_from_dataset(str(Path(__file__).resolve().parents[1] / "datasets" / "habits.json"))
    loaded = IntentMemory()
    single = next(row for row in habits if row["context"] == ["user:привет"])
    with learning_allowed():
        for _ in range(int(single["strength"])):
            loaded.record_trace(single["context"], single["action"])
    assert loaded._compute_context_signature(single["context"]) == hashlib.md5("user:привет".encode()).hexdigest()[:8]
    assert loaded.activate_by_context(["user:привет"]).get("сказать_привет", 0.0) > 0.0
    assert loaded.activate_by_context(["user:привет", "zone:floor"]).get("сказать_привет", 0.0) == 0.0

    legacy = hashlib.md5(b"hunger_high").hexdigest()[:8]
    old = IntentMemory.from_dict(
        {
            "traces": [
                {
                    "intent_type": "eat",
                    "context_signature": legacy,
                    "strength": 2.0,
                    "recency": 1.0,
                }
            ]
        }
    )
    assert old.activate_by_context(["zone:floor", "alarm_call", "hunger_high"]).get("eat", 0.0) > 0.0
    round_trip = IntentMemory.from_dict(memory.to_dict())
    assert round_trip._compute_context_signature(hungry) == hungry_key
    assert round_trip.activate_by_context(hungry).get("eat", 0.0) > 0.0


def test_habit_signature_ignores_pythonhashseed():
    script = """
import hashlib, os
from intent_memory import IntentMemory
memory = IntentMemory()
left = ["alarm_call", "zone:wheel", "hunger_high"]
right = ["hunger_high", "alarm_call", "zone:wheel"]
print(memory._compute_context_signature(left))
print(memory._compute_context_signature(right))
print(hashlib.md5(b"hunger_high").hexdigest()[:8])
print(os.environ.get("PYTHONHASHSEED"))
"""
    repo = Path(__file__).resolve().parents[1]
    seen = []
    for seed in ("0", "1", "7", "random"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = seed
        env["PYTHONPATH"] = str(repo / "src")
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=repo,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        lines = completed.stdout.strip().splitlines()
        seen.append(tuple(lines[:3]))
    assert len(set(seen)) == 1
    assert seen[0][0] == seen[0][1]
    assert seen[0][2] == hashlib.md5(b"hunger_high").hexdigest()[:8]


def _survival(seed: int, policy: str | None, steps: int = 30) -> dict:
    random.seed(seed)
    agent = ChinchillaAgent(
        sex="F",
        name="Luna",
        rng_seed=seed,
        physiology_as_policy=True,
        age=MATURITY_AGE_S,
        is_mature=True,
    )
    agent.replaced_policy_action = policy
    agent.hunger = 0.8
    agent.thirst = 0.75
    agent.wakefulness.wakefulness = 0.2
    agent.energy = 1.0
    agent.resources = SharedResources()
    agent.colony = [agent]
    lived = steps
    for index in range(steps):
        if agent.mortality_system.is_dead():
            lived = index
            break
        agent.sim_step(1.0)
    return {
        "dead": bool(agent.mortality_system.is_dead()),
        "cause": agent.mortality_system.cause_of_death,
        "lived": lived,
        "energy": round(float(agent.energy), 5),
        "sim": round(float(agent.sim_time), 5),
    }


def test_ablation_rest_loses_and_seed_is_deterministic():
    assert PHYSIOLOGY_AS_POLICY is True
    first = _survival(7, None)
    second = _survival(7, None)
    rest_a = _survival(7, "rest")
    rest_b = _survival(7, "rest")
    assert first == second
    assert rest_a == rest_b
    assert first["dead"] is False
    assert first["lived"] == 30
    assert rest_a["dead"] is True
    assert rest_a["cause"] == "exhaustion"
    assert rest_a["lived"] < 30
    for seed in (1, 42):
        core = _survival(seed, None)
        rest = _survival(seed, "rest")
        assert core["dead"] is False
        assert rest["dead"] is True
        assert rest["cause"] == "exhaustion"


def test_flag_off_keeps_body_gate_and_flag_on_leaves_choice():
    sleepy = ChinchillaAgent(sex="M", name="Milo", rng_seed=8, physiology_as_policy=False)
    sleepy.replaced_policy_action = "rest"
    sleepy.colony = [sleepy]
    sleepy.resources = SharedResources()
    sleepy.hunger = 0.1
    sleepy.thirst = 0.1
    sleepy.wakefulness.wakefulness = 0.95
    sleepy.sim_step(0.1)
    assert sleepy.current_action == "sleep"
    assert sleepy.is_sleeping is True

    thirsty = ChinchillaAgent(sex="M", name="Milo", rng_seed=9, physiology_as_policy=True)
    thirsty.replaced_policy_action = "rest"
    thirsty.colony = [thirsty]
    thirsty.resources = SharedResources()
    thirsty.hunger = 0.1
    thirsty.thirst = 0.95
    thirsty.wakefulness.wakefulness = 0.1
    thirsty.sim_step(0.1)
    assert thirsty.current_action == "rest"
    assert thirsty.thirst > 0.9


def _social_pair(flag: bool, action: str):
    resources = SharedResources()
    left = ChinchillaAgent(
        sex="F",
        name="Luna",
        rng_seed=1,
        physiology_as_policy=flag,
        position="floor",
        is_mature=True,
        age=MATURITY_AGE_S + 20,
    )
    right = ChinchillaAgent(
        sex="M",
        name="Milo",
        rng_seed=2,
        physiology_as_policy=flag,
        position="floor",
        is_mature=True,
        age=MATURITY_AGE_S + 20,
    )
    for agent, other in ((left, right), (right, left)):
        agent.resources = resources
        agent.colony = [left, right]
        agent.replaced_policy_action = action
        agent.hunger = 0.1
        agent.thirst = 0.1
        agent.wakefulness.wakefulness = 0.1
        agent.social_drive = 0.9
        agent.knowledge[other.agent_id] = KnownAgent(
            agent_id=other.agent_id,
            name=other.name,
            sex=other.sex,
            last_seen_position="floor",
            last_seen_time=0.0,
            familiarity=0.1,
            affinity=0.05,
            relationship_type="acquaintance",
        )
    offers = []
    for _ in range(6):
        left.sim_step(0.2)
        right.sim_step(0.2)
        offers.append(getattr(right.pending_offer, "offer_type", None))
    return offers


def test_social_layer_follows_the_flag():
    assert any(item for item in _social_pair(False, "rest"))
    assert _social_pair(True, "rest") == [None, None, None, None, None, None]
    assert any(item for item in _social_pair(True, "socialize"))


def test_core_births_keep_generated_names_and_rest_does_not():
    def pair(seed: int, policy: str | None):
        random.seed(seed)
        resources = SharedResources()
        female = ChinchillaAgent(
            sex="F",
            name="Luna",
            rng_seed=seed,
            physiology_as_policy=True,
            age=MATURITY_AGE_S + 10,
            is_mature=True,
            position="floor",
        )
        male = ChinchillaAgent(
            sex="M",
            name="Milo",
            rng_seed=seed + 1,
            physiology_as_policy=True,
            age=MATURITY_AGE_S + 10,
            is_mature=True,
            position="floor",
        )
        for agent in (female, male):
            agent.replaced_policy_action = policy
            agent.hunger = 0.2
            agent.thirst = 0.2
            agent.wakefulness.wakefulness = 0.1
            agent.energy = 1.0
            agent.resources = resources
            agent.social_drive = 0.9
            agent.lived_steps = 200
            agent.reproductive_system.reproductive_drive = 0.9
        female.colony = [female, male]
        male.colony = [female, male]
        female.heat_cycle._elapsed = HEAT_CYCLE_LENGTH_S - ESTRUS_DURATION_S + 5.0
        female.heat_cycle.update(0.0)
        for agent, other in ((female, male), (male, female)):
            agent.knowledge[other.agent_id] = KnownAgent(
                agent_id=other.agent_id,
                name=other.name,
                sex=other.sex,
                last_seen_position="floor",
                last_seen_time=0.0,
                familiarity=0.6,
                affinity=0.5,
                relationship_type="acquaintance",
            )
        return female, male

    core_f, core_m = pair(11, None)
    rest_f, rest_m = pair(11, "rest")
    births = []
    for _ in range(40):
        if not core_f.pending_offspring_list:
            core_m.sim_step(1.0)
            core_f.sim_step(1.0)
        rest_m.sim_step(1.0)
        rest_f.sim_step(1.0)
        if core_f.is_pregnant and core_f.gestation_timer > 2.0:
            core_f.gestation_timer = 1.0
        if core_f.pending_offspring_list and not births:
            births = list(core_f.pending_offspring_list)
    assert births
    assert rest_f.pending_offspring_list == []
    assert rest_f.is_pregnant is False
    for child in births:
        assert _NAME.match(child.name)
        assert child.physiology_as_policy is True
    gated_mother = ChinchillaAgent(sex="F", name="Luna", physiology_as_policy=False, is_mature=True)
    gated_child = gated_mother._create_offspring(None)
    assert gated_child.physiology_as_policy is False


def test_colony_save_roundtrip_and_missing_new_fields(tmp_path):
    runner = SimulationRunner()
    agent = ChinchillaAgent(
        sex="F",
        name="Luna",
        rng_seed=3,
        physiology_as_policy=True,
        age=12.0,
        is_mature=False,
        position="house",
    )
    agent.energy = 0.77
    agent.hunger = 0.4
    runner.add_agent(agent)
    storage = ColonyStorage(save_dir=tmp_path)
    gated = ChinchillaAgent(
        sex="M",
        name="Milo",
        rng_seed=4,
        physiology_as_policy=False,
        age=12.0,
        is_mature=False,
        position="floor",
    )
    runner.add_agent(gated)
    path = storage.save_colony(runner, "colony.json")
    raw = Path(path).read_text(encoding="utf-8")
    assert '"physiology_as_policy": true' in raw
    assert '"physiology_as_policy": false' in raw
    loaded = storage.load_colony(path)
    by_name = {item.name: item for item in loaded.agents}
    assert by_name["Luna"].position == "house"
    assert by_name["Luna"].energy == pytest.approx(0.77)
    assert by_name["Luna"].physiology_as_policy is True
    assert by_name["Milo"].physiology_as_policy is False

    payload = json.loads(raw)
    for row in payload["agents"]:
        row["runtime"].pop("physiology_as_policy")
    legacy_path = Path(tmp_path / "legacy_flag.json")
    legacy_path.write_text(json.dumps(payload), encoding="utf-8")
    legacy_flag = ColonyStorage(save_dir=tmp_path).load_colony(legacy_path)
    assert all(item.physiology_as_policy is True for item in legacy_flag.agents)

    stripped = Path(tmp_path / "old.json")
    text = raw.replace('"energy": 0.77', '"note": "legacy"')
    stripped.write_text(text, encoding="utf-8")
    legacy = ColonyStorage(save_dir=tmp_path).load_colony(stripped)
    assert legacy.agents[0].name == "Luna"
    legacy.agents[0].sim_step(0.1)


def test_old_episode_without_override_fields_still_sleeps(tmp_path):
    agent = _core()
    context = ["zone:floor"]
    episode_id = agent.commit_executed_transition(
        action="rest",
        reward=0.2,
        context_events=context,
        decided_action="rest",
        overridden=False,
    )
    exp = agent.hippocampus.get_experience(episode_id)
    del exp.overridden
    del exp.override_source
    del exp.decided_action
    storage = AgentStorage(save_dir=str(tmp_path))
    path = storage.save_agent(
        agent.hippocampus,
        agent.cortex,
        agent.selector,
        sleep_manager=agent.sleep_manager,
        agent=agent,
        filename="old_episode.pkl",
    )
    restored = _core()
    storage.load_agent(
        restored.hippocampus,
        restored.cortex,
        restored.selector,
        path,
        sleep_manager=restored.sleep_manager,
        agent=restored,
    )
    loaded = restored.hippocampus.get_experience(episode_id)
    assert loaded is not None
    assert not hasattr(loaded, "overridden")
    restored.sleep(cycles=1)
