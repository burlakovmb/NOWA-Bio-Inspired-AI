# Independent trajectories for judged body lessons

Русский: [vc-independent-lesson-trajectories.ru.md](vc-independent-lesson-trajectories.ru.md)

## Contract

`nowa_body.feedback_loop.store_lesson` represents an independently judged
context/action/outcome presentation. After a new episode is stored and before
`Agent._record_known_outcome`, assign:

```python
episode.trajectory_id = "vc-lesson:" + str(episode.episode_id)
episode.episode_step = 0
```

The native hippocampus supplies a unique resident `episode_id`. The derived
trajectory is unique within that mind, persists with the episode, and is
disjoint from native `traj-N` trajectories. Repeated presentations are separate
episodes. No counter, random draw, additional checkpoint field or core API is
introduced. A private helper permits a no-tag experimental control.

This applies to every `store_lesson` caller: mentor `BusinessAgentRuntime.teach`,
judged approvals/rejections, limit-block and strict-binding lessons. The lesson
describes its own judged situation, rather than extending the most recent
waking trajectory. This changes future body learning; loading an old mind does
not migrate its episodes.

## Reason

Sleep assigns causal credit inside each trajectory. With missing trajectory
metadata, independent lessons share the legacy empty-id group and use sample
positions. Timestamp sorting and repeated references can then put unrelated
lessons outside the credit window. An explicit independent trajectory at step
`0` gives its lesson depth `0`, including duplicated replay entries, without
changing the general-purpose core or its replay rules.

## Preserved behavior

- Public `store_lesson` and `teach` signatures, continuous reward/clamping,
  intensity, context, action, consequence and known-outcome call arguments.
- Existing `terminal=False` and self-bootstrap semantics. Trajectory identity
  alone does not change TD terminal semantics.
- Native `Agent._trajectory_id`, `_trajectory_seq`, `_trajectory_step` and
  `_trajectory_closed`. The body does not call `_mark_transition_trajectory`.
- Stable learning through `Agent.sleep()`; waking outcomes enter only the
  bounded labile tier. Metadata is episode state, not a stable learning update.
- Unjudged `_store_episode` calls and role seeders. They retain legacy semantics.
- Historical checkpoints and existing episodes. No retagging or load migration.
  Tagged and legacy episodes may coexist; legacy-group exclusions can remain.
- Core `src/`, root `tests/`, platform `src/mcp_body/` and the factory.

## Compatibility and persistence

Native `Experience` supports both writable, serialized fields. Real-core tests
must assert that every newly judged lesson is tagged before registration.
Do not silently invent an identifier when `episode_id` is absent/empty.
Supported lightweight test doubles still store their episodes; missing/read-only
metadata does not make their former storage path fail. If an assignment cannot
be completed, avoid leaving a misleading partial trajectory where the object's
supported attribute interface permits restoration. Do not swallow an error
from the actual known-outcome registration.

VC `save_mind`/`load_mind` retains both fields without a new sidecar. The native
episode-id allocator handles subsequent new lessons after restore. Old id-less
episodes remain id-less. Independently loaded minds keep separate namespaces.

## Code acceptance

Use synthetic, domain-free cases and strict learning. Verify:

1. Metadata is set before outcome registration; kwargs/signatures are preserved.
2. Repeated identical presentations get distinct deterministic trajectory ids;
   native trajectory state and RNG streams are unchanged.
3. Equal/unequal timestamps, more than the credit window's number of independent
   lessons, mixed rewards and duplicate object entries yield lesson depth `0`.
   An untagged negative control discriminates the former behavior; a mixed
   legacy/tagged sample isolates only the tagged lessons.
4. Stable state stays frozen awake; real sleep captures pending lessons and
   removes labile contributions without duplicate capture.
5. Save/restore retains tagged metadata, preserves legacy episodes and allows
   another independent lesson without collision.
6. Missing memory, storage returning `None`, id-less/read-only doubles, mentor
   teaching, judged feedback and the unjudged branch preserve their contracts.
7. Relevant body/onboarding/checkpoint tests and the VC fast regression suite
   pass; an independent reviewer checks the exact diff and evidence.

## Behavioral acceptance is separate

A new candidate class requires its own immutable plan and source/harness pins.
Keep the approved curriculum, baseline, schedule, reward, seeds and behavior
gates fixed. A tagging-disabled control must reproduce the previous time-aware
control before comparing candidates. Repeat candidate formation under another
hash seed; verify new-process restore and continued learning. Re-evaluate the
primary twice with the same decision RNG policy, validate complete grids, and
apply unchanged nonregression and unknown-budget criteria. A declared secondary
seed is report-only and cannot replace the main candidate.

Test success does not qualify an employee or authorize adopting a candidate,
automatic document creation or ERP writes. A new contract is not a repair or
reproduction of historical minds. Terminal semantics, role-prior trajectories,
a public core outcome API and professional qualification are separate work.

Related: [body lessons](issue-18-vc-body-lessons.en.md),
[two-tier plasticity](../architecture/two-tier-plasticity.en.md).
