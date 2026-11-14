"""Historical facts must survive loading without becoming rewarded actions."""
from copy import deepcopy
from pathlib import Path

import pytest

from nowa_body.employee_checkpoint import load_mind, save_mind
from nowa_body.historical_memory import observation_rows, store_observations
from nowa_body.onboarding import make_runtime
from learning_guard import stable_fingerprint

ROLE = Path(__file__).resolve().parents[1] / "src/nowa_roles/procurement/config.yaml"


def observation():
    return {"id": "receipt-test", "context_tokens": ["domain:procurement", "product:test"],
            "facts": {"quantity": "50", "authorized_budget": None},
            "provenance": {"source": "test fixture; not Company data"}}


def test_unjudged_actionless_roundtrip_and_idempotency(tmp_path):
    agent, _, _ = make_runtime(ROLE, "observation_buyer", 1)
    before = stable_fingerprint(agent)
    row = observation()
    assert store_observations(agent, [row])["inserted"] == 1
    assert store_observations(agent, [row])["already_present"] == 1
    assert len(agent.hippocampus.experiences) == 1
    episode = agent.hippocampus.experiences[0]
    assert not getattr(episode, "td_outcome_committed", False)
    assert not any(t.startswith("action:") for t in episode.path.signature())
    assert stable_fingerprint(agent) == before
    agent.sleep(cycles=3)
    assert not getattr(episode, "td_outcome_committed", False)
    assert not getattr(episode, "consolidated", False)
    path = tmp_path / "mind.nowa"
    save_mind(agent, path)
    restored, _, _ = make_runtime(ROLE, "observation_buyer", 1)
    load_mind(restored, path)
    assert observation_rows(restored) == {row["id"]: {"facts": row["facts"], "provenance": row["provenance"]}}


@pytest.mark.parametrize("change", ["action", "reward", "token", "source", "nan"])
def test_batch_rejected_before_any_memory_change(change):
    agent, _, _ = make_runtime(ROLE, "invalid_buyer", 1)
    invalid = deepcopy(observation())
    invalid["id"] = "invalid"
    if change in {"action", "reward"}:
        invalid[change] = 0
    elif change == "token":
        invalid["context_tokens"] = ["action:create_purchase_order"]
    elif change == "source":
        invalid["provenance"] = {}
    else:
        invalid["facts"]["quantity"] = float("nan")
    with pytest.raises(ValueError):
        store_observations(agent, [observation(), invalid])
    assert not agent.hippocampus.experiences


def test_capacity_and_conflicting_reimport_preserve_old_experience():
    agent, _, _ = make_runtime(ROLE, "bounded_buyer", 1)
    row = observation()
    store_observations(agent, [row])
    agent.hippocampus.max_experiences = 1
    other = deepcopy(row)
    other["id"] = "other"
    with pytest.raises(ValueError, match="evict"):
        store_observations(agent, [other])
    row["facts"]["quantity"] = "999"
    with pytest.raises(ValueError, match="changed"):
        store_observations(agent, [row])
    assert observation_rows(agent)["receipt-test"]["facts"]["quantity"] == "50"
