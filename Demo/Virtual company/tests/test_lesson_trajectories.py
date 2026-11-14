"""Independent VC lessons form isolated sleep-credit trajectories."""
from __future__ import annotations

import inspect
import random
from collections import Counter
from types import SimpleNamespace

import pytest

from agent_factory import AgentConfig, AgentFactory
from learning_guard import stable_fingerprint
from mcp_body.approval_gate import ApprovalStatus
from nowa_body.business_event_encoder import BusinessEventEncoder
from nowa_body.employee_checkpoint import load_mind, save_mind
from nowa_body.feedback_loop import (
    _mark_independent_lesson,
    _store_episode,
    apply_feedback_to_agent,
    store_lesson,
)
from nowa_body.runtime import BusinessAgentRuntime

WAIT = "wait_and_monitor"


@pytest.fixture(autouse=True)
def strict_learning(monkeypatch):
    monkeypatch.setenv("NOWA_STRICT_LEARNING", "1")


def _agent(agent_id="trajectory-test"):
    return AgentFactory(AgentConfig(actions=[WAIT])).spawn_default(agent_id=agent_id)


def _empty_runtime(agent):
    class EmptyRegistry:
        @staticmethod
        def motor_capabilities():
            return []

    return BusinessAgentRuntime(agent, EmptyRegistry(), None)


def _rng_state(agent):
    return (
        random.getstate(),
        agent._rng.getstate(),
        agent.sleep_manager._rng.getstate(),
        agent.affective_space.rng.getstate(),
    )


def _seed_rngs(agent, seed):
    random.seed(seed)
    agent._rng.seed(seed + 1)
    agent.sleep_manager._rng.seed(seed + 2)
    agent.affective_space.rng.seed(seed + 3)


def _tagged_lessons(agent, count, rewards=None):
    rewards = rewards or [0.7] * count
    return [
        store_lesson(agent, [f"synthetic:context:{index}"], WAIT, rewards[index], consequence="synthetic")
        for index in range(count)
    ]


def test_tags_before_known_outcome_and_preserves_public_contract(monkeypatch):
    agent = _agent()
    original_record = agent._record_known_outcome
    observed = []

    def record(**kwargs):
        episode = kwargs["episode"]
        observed.append((episode.trajectory_id, episode.episode_step, kwargs))
        return original_record(**kwargs)

    monkeypatch.setattr(agent, "_record_known_outcome", record)
    signature = inspect.signature(store_lesson)
    lesson = store_lesson(agent, ["synthetic:budget"], WAIT, 0.6, consequence="synthetic")

    assert str(lesson.episode_id)
    assert lesson.trajectory_id == f"vc-lesson:{lesson.episode_id}"
    assert lesson.episode_step == 0
    assert observed[0][0:2] == (lesson.trajectory_id, 0)
    kwargs = observed[0][2]
    assert set(kwargs) == {"context_events", "action_id", "outcome", "episode", "intensity"}
    assert "terminal" not in kwargs
    assert kwargs["context_events"] == ["synthetic:budget"]
    assert kwargs["action_id"] == WAIT
    assert kwargs["outcome"] == pytest.approx(0.6)
    assert kwargs["episode"] is lesson
    assert kwargs["intensity"] == pytest.approx(0.6)
    assert list(signature.parameters) == ["agent", "context_events", "action", "reward", "consequence"]
    assert signature.parameters["consequence"].default == "lesson"
    assert lesson.td_outcome_committed is True
    assert lesson.value_terminal is False


def test_repeated_lessons_are_unique_and_do_not_change_native_trajectory_counters():
    agent = _agent()
    first = agent.step(["synthetic:wake-1"], reward=0.2, dt=1.0)
    waking_episode = agent.hippocampus.experiences[-1]
    assert first == WAIT
    assert waking_episode.trajectory_id == "traj-1"
    assert waking_episode.episode_step == 0
    counters = (agent._trajectory_id, agent._trajectory_seq, agent._trajectory_step, agent._trajectory_closed)

    lessons = [store_lesson(agent, ["synthetic:repeat"], WAIT, 0.4) for _ in range(8)]
    assert all(item.trajectory_id == f"vc-lesson:{item.episode_id}" for item in lessons)
    assert all(item.episode_step == 0 for item in lessons)
    assert len({item.trajectory_id for item in lessons}) == len(lessons)
    assert all(not item.trajectory_id.startswith("traj-") for item in lessons)
    assert counters == (agent._trajectory_id, agent._trajectory_seq, agent._trajectory_step, agent._trajectory_closed)

    agent.step(["synthetic:wake-2"], reward=0.1, dt=1.0)
    next_waking_episode = agent.hippocampus.experiences[-1]
    assert next_waking_episode.trajectory_id == "traj-1"
    assert next_waking_episode.episode_step == 1
    assert agent._trajectory_seq == 1


def test_tagging_consumes_no_global_or_owned_rng_draws(monkeypatch):
    tagged = _agent("rng-tagged")
    control = _agent("rng-control")
    _seed_rngs(tagged, 7301)
    _seed_rngs(control, 7301)
    _tagged_lessons(tagged, 6, [0.8, -0.4, 0.3, -0.2, 0.5, 0.1])
    with monkeypatch.context() as patcher:
        patcher.setattr("nowa_body.feedback_loop._mark_independent_lesson", lambda _episode: False)
        _tagged_lessons(control, 6, [0.8, -0.4, 0.3, -0.2, 0.5, 0.1])
    assert _rng_state(tagged) == _rng_state(control)


def test_independent_depth_zero_for_varied_sequences_and_legacy_control():
    agent = _agent()
    rewards = [0.8, -0.02, 0.04, -0.06, 0.03, -0.01, 0.07, 0.02]
    lessons = _tagged_lessons(agent, 8, rewards)
    manager = agent.sleep_manager

    for index, lesson in enumerate(lessons):
        lesson.timestamp = float(index * 13)
    uneven = manager._assign_reward_anchored_causal_depth(lessons, 6)
    assert all(uneven[id(lesson)] == 0 for lesson in lessons)

    for lesson in lessons:
        lesson.timestamp = 50.0
    equal = manager._assign_reward_anchored_causal_depth(lessons, 6)
    assert all(equal[id(lesson)] == 0 for lesson in lessons)

    repeated = [lessons[0], lessons[3], lessons[0], lessons[7], lessons[3], lessons[0], lessons[5]]
    duplicate_refs = manager._assign_reward_anchored_causal_depth(repeated, 6)
    assert all(duplicate_refs[id(lesson)] == 0 for lesson in repeated)

    legacy_agent = _agent("legacy-depth-control")
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr("nowa_body.feedback_loop._mark_independent_lesson", lambda _episode: False)
        legacy = _tagged_lessons(legacy_agent, 8, rewards)
    for index, episode in enumerate(legacy):
        episode.timestamp = float(index)
    legacy_depths = manager._assign_reward_anchored_causal_depth(legacy, 6)
    assert any(legacy_depths[id(episode)] >= 6 for episode in legacy)

    mixed_depths = manager._assign_reward_anchored_causal_depth(lessons + legacy, 6)
    assert all(mixed_depths[id(episode)] == 0 for episode in lessons)
    assert any(mixed_depths[id(episode)] >= 6 for episode in legacy)


def test_real_sleep_keeps_stable_frozen_awake_and_captures_each_lesson_once(monkeypatch):
    agent = _agent()
    before = stable_fingerprint(agent)
    lessons = _tagged_lessons(agent, 3, [0.8, 0.6, 0.4])
    assert set(agent.labile._contributions) == {lesson.episode_id for lesson in lessons}
    assert stable_fingerprint(agent) == before

    calls = Counter()
    original = agent.sleep_manager._apply_episode_channel_and_habit

    def count_capture(episode, *args, **kwargs):
        calls[episode.episode_id] += 1
        return original(episode, *args, **kwargs)

    monkeypatch.setattr(agent.sleep_manager, "_apply_episode_channel_and_habit", count_capture)
    result = agent.sleep(cycles=3)

    assert not result.get("error")
    assert stable_fingerprint(agent) != before
    assert calls == Counter({lesson.episode_id: 1 for lesson in lessons})
    assert agent.labile._contributions == {}
    assert all(lesson.consolidated is True for lesson in lessons)


def test_tagged_and_legacy_trajectory_metadata_survive_checkpoint_roundtrip(tmp_path, monkeypatch):
    source = _agent("trajectory-persistence")
    with monkeypatch.context() as patcher:
        patcher.setattr("nowa_body.feedback_loop._mark_independent_lesson", lambda _episode: False)
        legacy = store_lesson(source, ["synthetic:legacy"], WAIT, 0.3)
    legacy_metadata = (hasattr(legacy, "trajectory_id"), getattr(legacy, "trajectory_id", None),
                       hasattr(legacy, "episode_step"), getattr(legacy, "episode_step", None))
    tagged = store_lesson(source, ["synthetic:new"], WAIT, 0.5)
    counters = (source._trajectory_id, source._trajectory_seq, source._trajectory_step, source._trajectory_closed)

    checkpoint = tmp_path / "synthetic-mind.nowa"
    save_mind(source, checkpoint)
    restored = _agent("trajectory-persistence")
    load_mind(restored, checkpoint)
    by_id = {episode.episode_id: episode for episode in restored.hippocampus.experiences}

    restored_legacy = by_id[legacy.episode_id]
    assert (hasattr(restored_legacy, "trajectory_id"), getattr(restored_legacy, "trajectory_id", None),
            hasattr(restored_legacy, "episode_step"), getattr(restored_legacy, "episode_step", None)) == legacy_metadata
    restored_tagged = by_id[tagged.episode_id]
    assert restored_tagged.trajectory_id == tagged.trajectory_id
    assert restored_tagged.episode_step == 0
    assert (restored._trajectory_id, restored._trajectory_seq, restored._trajectory_step,
            restored._trajectory_closed) == counters

    after_load = store_lesson(restored, ["synthetic:after-load"], WAIT, 0.7)
    assert after_load.trajectory_id == f"vc-lesson:{after_load.episode_id}"
    assert after_load.episode_step == 0


def test_approval_rejection_and_runtime_teach_are_tagged_but_unjudged_is_not():
    agent = _agent("all-judged-paths")
    runtime = _empty_runtime(agent)
    taught = runtime.teach(["synthetic:mentor"], WAIT, 0.5)
    assert taught.trajectory_id == f"vc-lesson:{taught.episode_id}"

    def feedback(status, decided_by="supervisor"):
        proposed = SimpleNamespace(tool_id="synthetic_action", intent_summary="synthetic", context_events=[])
        record = SimpleNamespace(
            proposed_action=proposed,
            status=status,
            decided_by=decided_by,
            execution_result={"status": "accepted"},
        )
        apply_feedback_to_agent(agent, record, BusinessEventEncoder())
        return agent.hippocampus.experiences[-1]

    approved = feedback(ApprovalStatus.APPROVED)
    rejected = feedback(ApprovalStatus.REJECTED)
    unjudged = feedback(ApprovalStatus.APPROVED, "system:auto")
    assert approved.trajectory_id == f"vc-lesson:{approved.episode_id}"
    assert rejected.trajectory_id == f"vc-lesson:{rejected.episode_id}"
    assert not getattr(unjudged, "trajectory_id", None)
    assert not getattr(unjudged, "episode_step", None)
    assert not getattr(unjudged, "td_outcome_committed", False)


def test_unsupported_stub_metadata_is_safe_and_partial_assignment_is_rolled_back():
    class PartialEpisode:
        def __init__(self):
            self.episode_id = "partial-stub"
            self.trajectory_id = "old-marker"

        def __setattr__(self, name, value):
            if name == "episode_step":
                raise AttributeError("read-only synthetic step")
            object.__setattr__(self, name, value)

    class ReadOnlyStepEpisode:
        def __init__(self):
            self.episode_id = "readonly-stub"

        @property
        def episode_step(self):
            return None

    class StubAgent:
        def __init__(self, episode):
            self.hippocampus = SimpleNamespace(store=lambda *_a, **_k: episode)
            self.outcomes = []
            self._record_known_outcome = lambda **kwargs: self.outcomes.append(kwargs)

    partial = PartialEpisode()
    result = store_lesson(StubAgent(partial), [], WAIT, 0.2)
    assert result is partial
    assert partial.trajectory_id == "old-marker"
    assert not hasattr(partial, "episode_step")

    readonly = ReadOnlyStepEpisode()
    result = store_lesson(StubAgent(readonly), [], WAIT, 0.2)
    assert result is readonly
    assert not hasattr(readonly, "trajectory_id")
    assert readonly.episode_step is None

    no_id = SimpleNamespace()
    result = store_lesson(StubAgent(no_id), [], WAIT, 0.2)
    assert result is no_id
    assert not hasattr(no_id, "trajectory_id") and not hasattr(no_id, "episode_step")

    empty_id = SimpleNamespace(episode_id="")
    assert _mark_independent_lesson(empty_id) is False
    assert not hasattr(empty_id, "trajectory_id") and not hasattr(empty_id, "episode_step")


@pytest.mark.parametrize("failed_field", ["trajectory_id", "episode_step"])
def test_mutate_then_raise_rolls_back_attempted_field_and_prior_write(failed_field):
    class MutateThenRaiseEpisode:
        def __init__(self):
            object.__setattr__(self, "episode_id", "mutate-then-raise")
            object.__setattr__(self, "trajectory_id", "legacy-marker")

        def __setattr__(self, name, value):
            object.__setattr__(self, name, value)
            if name == failed_field and value in {"vc-lesson:mutate-then-raise", 0}:
                raise AttributeError("synthetic post-write failure; restoration is supported")

    episode = MutateThenRaiseEpisode()
    assert _mark_independent_lesson(episode) is False
    assert episode.trajectory_id == "legacy-marker"
    # episode_step was absent before the attempted assignment, so rollback
    # must remove it; the test also exercises restoring trajectory_id when
    # the second field fails after the first field was written.
    assert not hasattr(episode, "episode_step")

    # Prove both old-value restoration and absent-field deletion are accepted
    # by this stub's public setter interface.
    episode.trajectory_id = "legacy-marker"
    assert episode.trajectory_id == "legacy-marker"


def test_missing_memory_and_none_store_return_remain_safe():
    assert store_lesson(SimpleNamespace(), [], WAIT, 0.2) is None
    called = []
    agent = SimpleNamespace(hippocampus=SimpleNamespace(store=lambda *_a, **_k: None),
                            _record_known_outcome=lambda **kwargs: called.append(kwargs))
    assert store_lesson(agent, [], WAIT, 0.2) is None
    assert _store_episode(agent, [], WAIT, 0.2, 0.2, "synthetic") is None
    assert called == []
