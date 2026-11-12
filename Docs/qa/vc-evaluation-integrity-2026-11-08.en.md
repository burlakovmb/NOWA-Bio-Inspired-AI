# VC evaluation integrity: P2 closure

Russian: [vc-evaluation-integrity-2026-11-08.ru.md](vc-evaluation-integrity-2026-11-08.ru.md)

The pure offline validator implements the
[artifact contract](../specs/vc-evaluation-integrity.en.md). It rejects missing,
duplicate, unknown and misclassified probe/age/seed keys; binds group and
expected action to frozen probes; derives correctness and all budget/summary
counts from choices; and checks nested summary types and denominators.
Arbitrary row order is supported. Callers receive complete validated maps,
not a potentially truncated positional comparison.

Implementation/test scope: `evaluation_contract.py` and
`test_evaluation_contract.py` in the VC body and test directories. No core,
employee memory, operational risk policy or external data is changed.
Input/plan/checkpoint/source authentication remains the caller's responsibility.

Author and coordinator each ran the supplied suite: `40 passed`; coordinator
time `0.59` s. Independent final acceptance executed the same `40` cases plus
`63` additional synthetic cases, all passing. Verdict: **PASS for scoped P2
closure of the public validator**, no P1/P2 findings. Additional coverage includes
length-preserving reclassification, omitted/duplicated rows, binding and type
tampering, dishonest summaries, reversed row order and unrecognized choices.

The independent reviewer did not implement the validator. Tests use synthetic
fixtures and the root `.venv`, with `PYTHONDONTWRITEBYTECODE=1` and
`PYTHONUTF8=1`. This result does not approve a private comparator integration,
a new learning experiment or a professionally qualified employee. Both
reference and candidate must actually pass validation before any acceptance
gate is evaluated. No seed, score threshold or curriculum was changed.
