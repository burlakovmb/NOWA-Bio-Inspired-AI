"""K01: a drink or a meal must follow the deficit, not the tick rate.

Selecting drink while not thirsty was taking a full sip every tick, so a
demo step (dt = 1/12 s) emptied the shared bowl in about a minute and a
1 s step emptied it before 600 s. Relief is real only when the need drops.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

COLONY_SRC = Path(__file__).resolve().parents[1] / "Demo" / "Colony chinchillas" / "src"
if str(COLONY_SRC) not in sys.path:
    sys.path.insert(0, str(COLONY_SRC))

from colony_agent import ChinchillaAgent  # noqa: E402
from genome import GenomeVector  # noqa: E402
from shared_resources import SharedResources  # noqa: E402
from simulation_runner import SimulationRunner  # noqa: E402


def test_unneeded_drink_and_eat_do_not_consume_shared_stocks() -> None:
    agent = ChinchillaAgent(sex="F", name="Luna", physiology_as_policy=True, rng_seed=1)
    agent.resources = SharedResources(food_pellets=1.0, hay=1.0, water=1.0)
    agent.colony = [agent]
    agent.hunger = 0.1
    agent.thirst = 0.1
    for _ in range(200):
        agent._interpret_action("drink")
        agent._interpret_action("eat")
    assert agent.resources.water > 0.95
    assert agent.resources.food_pellets + agent.resources.hay > 1.9

    agent.position = "waterer"
    agent.thirst = 0.9
    agent._interpret_action("drink")
    agent.position = "bowl_pellets"
    agent.hunger = 0.9
    agent._interpret_action("eat")
    assert agent.thirst < 0.5
    assert agent.hunger < 0.6
    assert agent.resources.water < 1.0
    assert agent.resources.food_pellets < 1.0


def test_failed_drink_is_not_rewarded_like_a_real_sip() -> None:
    agent = ChinchillaAgent(sex="M", name="Milo", physiology_as_policy=True, rng_seed=2)
    agent.resources = SharedResources(food_pellets=1.0, hay=1.0, water=0.0)
    agent.colony = [agent]
    agent.hunger = 0.2
    agent.thirst = 0.9
    agent.affective_space.axes["stress"] = 0.0
    agent.affective_space.axes["valence"] = 0.0
    before = agent._physiology_snapshot()
    agent._interpret_action("drink")
    reward = agent._compute_reward(before=before, executed_action="drink")
    assert agent.thirst == 0.9
    assert reward < 0.0


def _founders(seed: int):
    random.seed(seed)
    runner = SimulationRunner(death_journal_path=f"/tmp/colony-need-{seed}.jsonl")
    rng = random.Random(seed)
    for idx in range(4):
        runner.add_agent(
            ChinchillaAgent(
                sex="F" if idx % 2 == 0 else "M",
                generation=0,
                genome=GenomeVector.random(rng),
                physiology_as_policy=True,
                rng_seed=seed * 10 + idx,
            )
        )
    return runner


def test_demo_step_does_not_empty_water_in_the_first_minute() -> None:
    runner = _founders(1)
    runner.run_for(80.0, dt=1.0 / 12.0)
    assert len(runner.agents) == 4
    assert runner.total_deaths == 0
    assert runner.resources.water > 0.4
    assert max(agent.thirst for agent in runner.agents) < 0.9


def test_founders_live_600s_at_one_second_steps() -> None:
    for seed in (1, 2, 7):
        runner = _founders(seed)
        runner.run_for(600.0, dt=1.0)
        assert runner.total_deaths == 0, seed
        assert len(runner.agents) == 4
        assert runner.resources.water > 0.05
        assert max(agent.thirst for agent in runner.agents) < 0.95
        assert max(agent.hunger for agent in runner.agents) < 0.95
        assert min(agent.energy for agent in runner.agents) > 0.2
