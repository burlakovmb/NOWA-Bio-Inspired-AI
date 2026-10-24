# Body layer — lessons filed under the situation

Russian: [NOWA_Body_Lessons.ru.md](NOWA_Body_Lessons.ru.md)

Modules (`Demo/Virtual company/src/nowa_body/`): `feedback_loop.py`, `runtime.py` (`BusinessAgentRuntime`, a subclass of the platform runtime), `strict_binder.py`, `business_event_encoder.py`. Stdlib only.
Related: #18 (feedback quantization), [Docs/architecture/two-tier-plasticity.en.md](../../../Docs/architecture/two-tier-plasticity.en.md).

The core is not changed: neither the cognitive modules nor the platform body layer `src/mcp_body/`. The employee extends the platform classes (`BusinessAgentRuntime`, `SchemaBinder`, `GenericEncoder`, `ProposedAction`) in the demo. The mechanisms below are domain-free; whether any of them belongs in `mcp_body` is the maintainer's decision.

---

## 1. Problem

Running a body-layer agent (the Virtual company buyer, in its simulator) for weeks showed that the body did not give the mind the situation an outcome belongs to:

1. Approval feedback was stored without the context the decision was made in, so a lesson could not be recalled in the same situation later.
2. A rejected call was stored as "this tool, negative reward". The hippocampus pulls toward the action a recalled episode holds whatever the sign, so a rejection still pulled toward calling the tool.
3. Calls the gate executed by itself (no person decided) were stored as full approvals.
4. There was no way to file a lesson that is not the latest step (a later verdict, a mentor's correction). `apply_feedback_to_last_experience` takes only the last step and quantizes the rating (#18).
5. When the role says where a parameter comes from and the world has nothing there, the binder guessed elsewhere and produced a call on the wrong entity.
6. Generic `tool:/status:/field:/entity:` tokens filled every context, so a lesson written in named events matched the live context at a fraction of its similarity.

## 2. Outcomes filed under the decision context

- `ContextualProposedAction` (a `ProposedAction` with `context_events`): the runtime copies the context tokens the mind decided on into the proposal.
- `apply_feedback_to_agent(agent, record, encoder)`:

| Record | Stored |
| --- | --- |
| Approved / modified by a person | `store_lesson(context + outcome tokens, tool_id, reward)` (`1.0` / `0.4`) |
| Rejected | `store_lesson(context, wait_and_monitor, 1.0, consequence="call_rejected")` — "here, wait"; `record_action_outcome(tool_id, -1.0)` updates selection counts |
| Executed by the gate itself (`decided_by` starts with `system:`) | Faint episode: reward `0`, intensity `UNJUDGED_INTENSITY = 0.1`, no outcome tag |
| Expired | `store_lesson(context + outcome tokens, tool_id, -0.2)` |

## 3. `store_lesson` and `BusinessAgentRuntime.teach`

`store_lesson(agent, context_events, action, reward, consequence)` stores `context → action → consequence` as a hippocampal episode (reward clamped to `[-1, 1]`, intensity `|reward|`) and hands the outcome to the core through `Agent._record_known_outcome(context_events, action_id, outcome, episode, intensity)`, as the Tamagochi host does. That writes the labile tag on the continuous reward and marks the episode for capture in the next sleep; `stable_fingerprint` does not change while awake. Without a two-tier core (a stub) the episode is still stored.

`runtime.teach(context, action, reward, consequence)` is the same path, for the body's own lessons (§4) and for hosts.

The continuous reward avoids the 5-level quantization of `apply_feedback_to_last_experience` (#18) on this path; the core defect itself is not touched here.

## 4. Strict `param_bindings`

```yaml
param_bindings:
  slot_id: {path: entities.items.0.id, strict: true}
```

A strict binding takes its value only from its path. If the path is empty, `StrictSchemaBinder.bind` returns `None` and sets `last_strict_miss` to the first required parameter that missed. The runtime then files `teach(context, wait_and_monitor, STRICT_MISS_LESSON_REWARD = 0.5, consequence="nothing_to_bind")` — the world said there is nothing to act on — and reports `strict_miss` in the cycle result. Non-strict bindings keep the old fallback.

## 5. Seeds

No change. An earlier version of this PR stored a role's seeds at stability `1.0` so they would survive the first sleep; that bypassed sleep consolidation (review of #50). On the two-tier core it is not needed. A 5-seed matrix (Virtual company buyer, hard world, 30 simulated days) gives the same results with ordinary seeds — day-30 probe 84 ± 2 vs 83 ± 3, lost sales 448 ± 92 vs 452 ± 86, overspend 0 — and the first night moves them into the cortex (10–12 patterns after day 1 vs 1–3 at stability `1.0`). Seeds stay ordinary hippocampal episodes (state tier); `HippocampusSeeder` is unchanged.

## 6. `token_rules.generic_tokens`

`BusinessEventEncoder(token_rules={"generic_tokens": False})` keeps only mapped business events (`event:*`, valence/arousal/tags of the affective mapping) and drops the generic `tool:/status:/field:/entity:` tokens. Default `True` keeps the old behaviour, so a role without an event classifier still works.

## 7. Tests

`Demo/Virtual company/tests/test_body_lessons.py` (strict learning, domain-free): `store_lesson` files context, action and consequence; writes the labile tier only; continuous and clamped reward; stub agent; no memory → `None`; `teach` is the same path. Approval filed under the decision context; rejection is a "wait" lesson with `call_rejected`; unjudged execution is faint and untagged. Strict binding does not guess, non-strict still does, strict reads its path; the runtime files "waiting was right" on a strict miss. Generic tokens on by default, off keeps only named events.

## 8. Out of scope

- `apply_feedback_to_last_experience` quantization (#18) in the core.
- Any change to the platform `mcp_body`.
- Domain configuration (which events, bindings and seeds a role uses) — role config, tested in the demo.
