from __future__ import annotations

from agent_knowledge import KnownAgent
from colony_agent import ChinchillaAgent
from simulation_runner import SimulationRunner


def _link_known(observer: ChinchillaAgent, target: ChinchillaAgent, *, familiarity: float, affinity: float) -> None:
    observer.knowledge[target.agent_id] = KnownAgent(
        agent_id=target.agent_id,
        name=target.name,
        sex=target.sex,
        last_seen_position=target.position,
        last_seen_time=observer.sim_time,
        familiarity=familiarity,
        affinity=affinity,
        relationship_type="acquaintance" if familiarity > 0 else "stranger",
    )


def test_tc02_first_meeting_of_strangers() -> None:
    runner = SimulationRunner()
    a0 = ChinchillaAgent(sex="F", position="floor", rng_seed=1)
    a1 = ChinchillaAgent(sex="M", position="floor", rng_seed=2)
    runner.add_agent(a0)
    runner.add_agent(a1)

    # The test checks the first meeting, not wandering.
    for _ in range(10):
        a0._set_position("floor")
        a1._set_position("floor")
        runner.tick(1.0)

    assert a1.agent_id in a0.knowledge
    known = a0.knowledge[a1.agent_id]
    assert known.familiarity > 0.1
    assert known.relationship_type == "acquaintance"
    assert any(ep.interaction_type == "sniff_greet" for ep in known.interaction_history)


def test_tc05_position_knowledge_degrades_without_contact() -> None:
    runner = SimulationRunner()
    # Frozen interpretation cannot eat. Keep the gate so unmet hunger does not
    # end the decay window early.
    a0 = ChinchillaAgent(sex="F", position="wheel", physiology_as_policy=False)
    a1 = ChinchillaAgent(sex="M", position="wheel", physiology_as_policy=False)
    runner.add_agent(a0)
    runner.add_agent(a1)
    runner.run_for(10.0, dt=1.0)

    known = a0.knowledge[a1.agent_id]
    known.last_seen_position = "wheel"
    known.position_confidence = 1.0
    a0.position = "door"
    a1.position = "house"
    a0._interpret_action = lambda action: None  # type: ignore[method-assign]
    a1._interpret_action = lambda action: None  # type: ignore[method-assign]

    runner.run_for(120.0, dt=1.0)

    assert known.last_seen_position == "wheel"
    assert known.position_confidence < 0.5


def test_tc06_hearsay_spreads_between_familiar_agents() -> None:
    runner = SimulationRunner()
    agent_a = ChinchillaAgent(sex="F", position="floor")
    agent_b = ChinchillaAgent(sex="M", position="floor")
    agent_c = ChinchillaAgent(sex="F", position="shelf_upper")
    runner.add_agent(agent_a)
    runner.add_agent(agent_b)
    runner.add_agent(agent_c)

    _link_known(agent_a, agent_b, familiarity=0.8, affinity=0.4)
    _link_known(agent_b, agent_a, familiarity=0.8, affinity=0.4)
    _link_known(agent_b, agent_c, familiarity=0.8, affinity=0.5)
    _link_known(agent_c, agent_b, familiarity=0.7, affinity=0.4)

    agent_b._exchange_knowledge(agent_a)

    assert agent_c.agent_id in agent_a.knowledge
    hearsay_known = agent_a.knowledge[agent_c.agent_id]
    assert hearsay_known.memory_confidence < 0.6
    assert any(item.source_id == agent_b.agent_id for item in hearsay_known.hearsay)


def test_tc08_alarm_call_affects_known_stronger_than_unknown() -> None:
    a = ChinchillaAgent(sex="F")
    b = ChinchillaAgent(sex="M")
    c = ChinchillaAgent(sex="F")
    for agent in (a, b, c):
        agent.colony = [a, b, c]

    _link_known(b, a, familiarity=0.7, affinity=0.4)
    a.affective_space.axes["stress"] = 0.9
    b_start = b.stress
    c_start = c.stress

    b._perceive_alarm_calls()
    c._perceive_alarm_calls()

    b_delta = b.stress - b_start
    c_delta = c.stress - c_start
    assert b_delta > c_delta
    assert b.knowledge[a.agent_id].last_seen_affect == "fearful"
