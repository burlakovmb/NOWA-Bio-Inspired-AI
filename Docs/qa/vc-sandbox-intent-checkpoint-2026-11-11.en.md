# Sandbox IntentMemory checkpoint failures — 2026-11-11

Russian: [vc-sandbox-intent-checkpoint-2026-11-11.ru.md](vc-sandbox-intent-checkpoint-2026-11-11.ru.md).

## Scope and behavior

Addresses the sandbox checkpoint feedback in [PR #67](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/67#issuecomment-6800632152), against base `9c95f0282bb289e6c56bb9781492f432958b316a`.

- `_save_intent_memory_extension` serializes into a unique temporary sibling, flushes and synchronizes the file, closes it, then uses `os.replace`. Failed serialization or publication leaves the file intact at the extension-helper boundary and removes temporary output where possible; cleanup failure is warned.
- `_load_intent_memory_extension` contains optional read/decoding/shape errors. A missing key remains quiet legacy compatibility. Invalid extension data keeps existing habits, reports a warning, and does not abort successful base restoration. Conversion precedes publication; failed reference assignment rolls back the previous agent/manager references where their setters permit restoration.
- Empty valid habit collections and legacy trace mappings remain accepted. No core persistence schema or learning parameters change.
- The two duplicate GitHub-comment documents under `Docs/specs/hippocampal-decay-github-draft-2026-11-09.*` are removed. [The technical decay report](hippocampal-decay-persistence-2026-11-09.en.md) and the posted #16 evidence remain.

Implementation: `Demo/Virtual company/src/nowa_sandbox/sandbox_checkpoint.py`. New failure coverage: `Demo/Virtual company/tests/test_sandbox_checkpoint_intent_memory.py`. Contract: [issue #58](../specs/issue-58-sandbox-two-tier-plasticity.en.md).

## Executed verification

- Before the fix, a bounded new-test run produced `3 failed, 8 deselected`: live-file truncation during serialization, partial file loss on serialization failure, and invalid optional data replacing existing habits. The first setup attempt lacked the parent temporary directory and was an environment error, not defect evidence; the corrected run supplies the evidence above.
- Focused run: `35 passed, 9.06 s`, covering the new failures and existing sandbox checkpoint roundtrips, real learned habits, restored labile references, legacy files, genome and RNG metadata.
- Command from repository root: `.venv/Scripts/python.exe -m pytest -q "Demo/Virtual company/tests/test_sandbox_checkpoint_intent_memory.py" "Demo/Virtual company/tests/test_sandbox_checkpoint.py" --basetemp <scratch>`.
- Environment: Python `3.14`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUTF8=1`, `NOWA_STRICT_LEARNING=1`, `SDL_VIDEODRIVER=dummy`, `SDL_AUDIODRIVER=dummy`.
- VC fast regression: `942 passed, 1 skipped, 6 deselected, 10 warnings`, `106.39 s`. Command from repository root: `.venv/Scripts/python.exe -m pytest -q -x -m "not slow and not perf" "Demo/Virtual company/tests" --basetemp <scratch>`. `TEMP` and `TMP` pointed to dedicated workspace scratch. Warnings concern existing synthetic role seed-corpus validation.
- The first independent review found one P2: the core silently skips malformed trace rows, so a shallowly valid extension could replace existing habits with an empty memory. The correction now validates each row's mapping shape and nonempty string `intent_type` / `context_signature` before conversion, including legacy mappings. Four malformed-row regressions and two valid nonempty list/mapping cases were added.
- Final focused run after that correction: `41 passed, 15.49 s`. The new failure module now contains `25` cases.
- Final VC fast regression after the row-validation correction: `948 passed, 1 skipped, 6 deselected, 10 warnings`, `118.06 s`, using the same fast-suite command and environment with fresh scratch.
- Independent final review: **PASS**, `47 passed, 16.77 s` (`41` checkpoint cases plus `6` independent native-memory probes). The initial P2 is closed, with no remaining P1/P2 findings within the bounded scope. Independent probes also verify flush/fsync/closed-before-replace ordering, unique sibling names, cleanup warning without masking the original failure, and partial setter mutation rollback. The full VC fast result is separate implementer evidence.

Reviewed worktree SHA-256 on `2026-11-11`:
- `sandbox_checkpoint.py`: `03d4bb73e12b75a937d78928a413c4554c378994fc299d23b2141d029bb427e6`.
- `test_sandbox_checkpoint_intent_memory.py`: `54b1c487aeb588f453bc454b4a2a78e154d3e2910c8b12ec5c77dbb71b7175c3`.

These identify the reviewed worktree bytes. Git LF/CRLF conversion can change a
checkout's byte hash without changing code; verify normalized content when
comparing across line-ending conversions.

## Limits

This change makes the extension write atomic; it does not turn the complete metadata + agent-file pair into a transaction or make the preceding base save atomic. It cannot recover a damaged base checkpoint. Trusted local pickle assumptions remain unchanged.

Full five-seed Stage 1a/1b qualification remains outstanding under #58. No trained employee is qualified, adopted, retrained or repaired by this change. At the time of this report, labile/plasticity rebind still depended on demo workarounds pending core #68; that correction now lives in `AgentStorage.load_agent` / `Agent.sleep()`. `IntentMemory` relink via `sandbox_intent_memory` remains a demo checkpoint concern. Optional clock, lesson-repeat and trajectory-helper changes are outside this correction.
