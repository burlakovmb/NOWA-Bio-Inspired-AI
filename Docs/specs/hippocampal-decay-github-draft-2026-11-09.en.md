# Hippocampal decay: evidence and acceptance for issue #16

Date: 2026-11-09. [Published supplement to issue #16](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/16#issuecomment-6745692962).
Technical report: [decay-clock persistence](../qa/hippocampal-decay-persistence-2026-11-09.en.md).

This document records the narrow counterexample and acceptance criteria
within the existing persistence issue. The body between the markers is
unchanged from the published bilingual comment.

<!-- github-body:start -->
### Description
This supplies an executed, narrowly scoped counterexample for the hippocampal
signature-persistence part of [#16](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/16).
The existing issue already covers missing signatures across save/load;
this is additional evidence and an explicit acceptance case within that work.

An episode's decayed `activation_energy` is saved, but its signature's
`last_decay_ts` is not. On restoration, the signature uses the older
`last_activated` as its decay anchor. At the same time value, it can apply
the already accounted interval again.

### Code evidence
Checked against upstream main `ff01ddcd6966e7298ed789e33fd4106fb05d16da`
on 2026-11-09:
- [Saved hippocampal payload](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/blob/ff01ddcd6966e7298ed789e33fd4106fb05d16da/src/storage.py#L28-L35).
- [Reconstructed decay anchor](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/blob/ff01ddcd6966e7298ed789e33fd4106fb05d16da/src/hippocampus.py#L578-L588).
- [Decay changes energy and signature clock](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/blob/ff01ddcd6966e7298ed789e33fd4106fb05d16da/src/hippocampus.py#L640-L668).
- [Episode serialization](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/blob/ff01ddcd6966e7298ed789e33fd4106fb05d16da/src/experience.py#L334-L341).

### Reproduction and verification status
The following standalone synthetic example uses the core only. Put `src`
on `PYTHONPATH`. It writes only a temporary checkpoint; it constructs no
Agent and executes no decisions, learning, sleep or application data.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from unittest.mock import patch
from experience import Experience, Path as EventPath, Event, EventType
from hippocampus import NOWAHippocampus
from storage import AgentStorage

base = 1_790_000_000.0
with patch("time.time", return_value=base):
    episode = Experience(EventPath([Event("synthetic", EventType.CONTEXT)]))
episode.episode_id = "synthetic-1"
episode.activation_energy = 1.0
live = NOWAHippocampus()
live.experiences = [episode]
live._ensure_signature_store()
with patch("time.time", return_value=base + 3600):
    live._apply_decay()

with TemporaryDirectory(prefix="decay-contract-") as folder:
    storage = AgentStorage(folder)
    cortex = NS(patterns={})
    selector = NS(actions=[], confidence_threshold=0.0, action_metadata={})
    storage.save_agent(live, cortex, selector, filename="synthetic.pkl")
    restored = NOWAHippocampus()
    storage.load_agent(restored, cortex, selector, str(Path(folder) / "synthetic.pkl"))
    restored._ensure_signature_store()
    with patch("time.time", return_value=base + 3600):
        live._apply_decay()
        restored._apply_decay()
    continuous = live.experiences[0].activation_energy
    reloaded = restored.experiences[0].activation_energy
    assert abs(continuous - 0.5485) < 1e-12
    assert abs(reloaded - 0.30085225) < 1e-12
    print({"continuous": continuous, "reloaded": reloaded})
```

Observed: continuous `0.5485`, restored `0.30085225`. Expected: the
restoration boundary alone must leave both at `0.5485` at that unchanged
time. The second calls use exactly the same clock value, so a differently
partitioned decay schedule does not explain the result.

The example was executed, and independent synthetic review reproduced the
same failure. This proves this persistence invariant fails; it does not
establish an effect on any employee's choices. It does not re-run the
historical pressure figures in #16 or prove full-mind equivalence.

### Suggested fix and acceptance
Preserve the decay anchor consistently with the already decayed energy.
The maintainer should choose the schema and compatibility rule; do not
silently repurpose `last_activated`, which represents actual activation.

- Same-time save/load and repeated save/load must not apply decay twice.
- Continuous and restored instances must agree after the same subsequent
  elapsed time and the same sequence of decay calls.
- Legacy saves without the new anchor must have an explicit, tested
  fallback/migration policy. Do not claim an unsaved historical anchor can
  always be recovered exactly.
- Keep episode identity and activation-time semantics intact; preserve
  the core's intended wall-clock policy.

Full decision-state roundtrip coverage in #16 remains a wider acceptance
requirement; this small synthetic test supplements it.

### Priority / estimate
Suggested priority: **medium**, consistent with #16; work package **wp2**.
Implementation effort should be assessed with #16/#31 rather than assigned
a new speculative token estimate.

### Related and non-overlapping scope
- [#16](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/16): parent persistence work; preferred place for this evidence.
- [#31](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/31): format security may share schema work, but this reproduction does not fix unsafe deserialization.
- [#14 scope clarification](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/14#issuecomment-6385597592): core wall time is intentional; freezing time here is a test control, not a proposal to change that policy.
- [#65](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/65) / [PR #66](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/66): colony genome/lineage persistence is a different state/path.
<!-- github-body:end -->
