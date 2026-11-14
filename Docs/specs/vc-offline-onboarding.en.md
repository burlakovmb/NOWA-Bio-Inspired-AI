# Virtual company: offline onboarding and memory persistence

Russian: [vc-offline-onboarding.ru.md](vc-offline-onboarding.ru.md)

## Scope

This is an implementation checkpoint, not a qualified purchasing policy.
NOWA learns and decides locally without an external LLM in its operational
loop. Development assistants may prepare approved lessons and inspect tests.
Their documents and chats are not the employee's learned memory.

Implementation: `Demo/Virtual company/src/nowa_body/onboarding.py`,
`historical_memory.py`, `employee_checkpoint.py`, and the optional
`nowa_roles/procurement/outcome_judge.py`. See the
[version and verification report](../qa/vc-onboarding-snapshot-2026-11-08.en.md).

## Judged lessons and offline commands

The CLI is `python -m nowa_body.onboarding` with VC `src` on `PYTHONPATH`.
Modes: `train`, `practice`, `evaluate`; all take `--employee-dir`.
`train` also requires `--role` and `--corpus`; `evaluate` requires `--probes`.
`practice --cycles` accepts `1` through `10` and refuses a superseded phase.

Each lesson has a unique `id`, nonempty observation `context_tokens`, an action
in the role vocabulary, finite `reward` in `[-1, 1]`, `consequence`, and
`provenance.source`. Context cannot include `action:` answer tokens. Training
refuses an existing employee directory. Frozen corpus hashes, per-cycle
checkpoints and lesson journals preserve provenance. Existing-role or mind
hash changes cause practice/evaluation to refuse the incompatible input.

Lessons use `runtime.teach` and `_record_known_outcome`; stable parameters
must stay unchanged while awake. Consolidation enters `Agent.sleep`, followed
by a checkpoint. The CLI enables `NOWA_STRICT_LEARNING=1` and an audit hook
rejecting network connections/listeners, subprocesses and shell execution.
The library functions rely on their caller to install equivalent guards.

The legacy CLI does not define a coherent simulated teaching schedule or
persist all private replay RNG streams. It is not the approved runner for a
new controlled recovery experiment. Evaluation leaves the mind file unchanged
but writes reports. It compares decisions using explicit `dt` and process-local
memory ages anchored to checkpoint modification times; this is a development
probe, not proof of operational retention or professional qualification.

## Unjudged observations

`store_observations` validates a whole batch before insertion. Records contain
only `id`, `context_tokens`, `facts`, and `provenance`. Duplicate unchanged
evidence is idempotent; changed evidence or capacity overflow is rejected.
Historical facts become context-only episodes with no known outcome, action
or fabricated reward. The source corpus and eligibility checks remain the
caller's responsibility. Episodic storage alone does not establish usable skill.

## Checkpoints and optional delayed feedback

Employee `save_mind` preserves `IntentMemory` under `vc_intent_memory` in the
same atomic checkpoint. Sandbox persistence uses `sandbox_intent_memory`.
Load accepts legacy files without these keys. Core `AgentStorage.load_agent`
([#68](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/68),
`_bind_restored_two_tier` in `src/storage.py`) reconnects each sleep manager's
`labile` and `plasticity` to the restored agent objects; `Agent.sleep()` does
the same before consolidation. Demo checkpoint adapters restore `IntentMemory`
from `vc_intent_memory` / `sandbox_intent_memory` and relink
`intent_memory` on the agent and manager; core does not persist intent memory.
The reference correction protects future sleep; it does not repair missed
historical capture.
Load only trusted local `.nowa` / `.ckpt` files written by this build (`nowa-agent-state` schema `1`, sandbox checkpoint schema `2`). Legacy pickle saves are rejected.

A role may supply `outcome_judge: module:factory`; composition selects the first
nonempty judge in role order. Its `observe` method returns lessons about delayed
consequences. The procurement judge is disabled by default. Its heuristics and
transient tracking are experimental, not a substitute for approval, budget
validation, persistent operation tracking or Company rules.

Employee minds, corpora, experimental output, credentials, personal notes and
local agent/tool settings stay outside repository commits. The committed tests
use synthetic fixtures. No ERP write or live employee activation is implied.
