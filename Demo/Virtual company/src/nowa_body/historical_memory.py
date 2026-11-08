"""Unjudged external observations in an employee's real episodic memory.

A historical receipt is neither an action performed by this employee nor a
known reward. No ACTION event or TD outcome is created. Durable raw evidence
belongs in an audited corpus as well; this bounded memory is not an ERP mirror.
"""
from __future__ import annotations

import json

from ._compat import ensure_core_src_on_path

ensure_core_src_on_path()
from experience import Event, EventType, Path
from learning_guard import stable_fingerprint

from .feedback_loop import UNJUDGED_INTENSITY

IDENTIFIER = "historical_observation:"
FACT = "historical_fact:"


def observation_rows(agent) -> dict[str, dict]:
    """Recover exact fact payloads without a model or a business tool call."""
    result = {}
    for episode in agent.hippocampus.experiences:
        names = episode.path.signature()
        identifiers = [name[len(IDENTIFIER):] for name in names if name.startswith(IDENTIFIER)]
        payloads = [name[len(FACT):] for name in names if name.startswith(FACT)]
        if identifiers and payloads:
            if len(identifiers) != 1 or len(payloads) != 1 or identifiers[0] in result:
                raise ValueError("ambiguous historical observation in memory")
            result[identifiers[0]] = json.loads(payloads[0])
    return result


def store_observations(agent, observations: list[dict]) -> dict:
    """Validate a whole batch before storing facts, preserving existing episodes.

    Caller owns checkpoints, source-scope checks, corpus and provenance journal.
    Capacity overflow is refused instead of evicting prior employee experience.
    Reimport of the same id and payload is idempotent; changed evidence fails.
    """
    if not isinstance(observations, list) or not observations:
        raise ValueError("a nonempty observation list is required")
    existing = observation_rows(agent)
    seen = set()
    pending = []
    for row in observations:
        if not isinstance(row, dict) or set(row) != {"id", "context_tokens", "facts", "provenance"}:
            raise ValueError("observations require only id, context_tokens, facts, provenance")
        identifier = row["id"]
        tokens = row["context_tokens"]
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError("unique nonempty observation ids are required")
        seen.add(identifier)
        if not isinstance(tokens, list) or not tokens or any(
            not isinstance(t, str) or not t or t.startswith(("action:", IDENTIFIER, FACT)) for t in tokens
        ):
            raise ValueError("observation context cannot contain action or internal markers")
        if not isinstance(row["facts"], dict) or not row["facts"] or not isinstance(row["provenance"], dict) or not row["provenance"].get("source"):
            raise ValueError("facts and source provenance are required")
        payload = {"facts": row["facts"], "provenance": row["provenance"]}
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        if identifier in existing:
            if existing[identifier] != payload:
                raise ValueError("an existing observation's evidence changed")
        else:
            pending.append((identifier, tokens, encoded))
    if len(agent.hippocampus.experiences) + len(pending) > agent.hippocampus.max_experiences:
        raise ValueError("historical import would evict existing employee experience")
    before = stable_fingerprint(agent)
    for identifier, tokens, payload in pending:
        path = Path()
        for token in [IDENTIFIER + identifier, *tokens, FACT + payload]:
            path = path.add_event(Event(token, EventType.CONTEXT))
        episode = agent.hippocampus.store(path, consequence=Event("observed_not_judged", EventType.CONSEQUENCE),
                                          intensity=UNJUDGED_INTENSITY, reward=0.0)
        if getattr(episode, "td_outcome_committed", False):
            raise RuntimeError("an unjudged observation acquired a known outcome")
    if stable_fingerprint(agent) != before:
        raise RuntimeError("observation import changed stable memory while awake")
    return {"inserted": len(pending), "already_present": len(observations) - len(pending),
            "stable_unchanged": True, "judged_rewards": 0}
