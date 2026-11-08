# VC evaluation artifact integrity

Russian: [vc-evaluation-integrity.ru.md](vc-evaluation-integrity.ru.md)

## Problem and boundary

A comparator must not claim non-regression after iterating a truncated `zip`
or trusting a separately stored budget summary. Validate both reference and
candidate before scoring. This is an offline artifact contract; no employee,
ERP, file access, network or external LLM is needed by the validator.

Implementation: `Demo/Virtual company/src/nowa_body/evaluation_contract.py`.
Public function: `validate_evaluation(evaluation, *, probes_by_set, seeds,
ages, unknown_budget_groups, order_action)`. Return a tuple containing a row
map keyed by `(set, id, age_s, seed)` and the recomputed summary. Invalid input
raises `ValueError`; no partial result or acceptance verdict is returned.
Callers must separately verify frozen input/plan/checkpoint/code hashes.

## Completeness and binding

- Each declared dataset has a nonempty frozen probe list with unique `id`
  and nonempty `group` and `expected_action`. Seeds and ages are nonempty unique integer
  lists; booleans are not integers, and ages are nonnegative.
- Each result row contains exactly `set`, `id`, `age_s`, `seed`, `group`,
  `expected`, `chosen`, `correct`. Identifier/action/group fields are nonempty
  strings; `correct` is a boolean; age and seed are integers, excluding booleans.
- Require exactly the complete Cartesian product of frozen probes, ages and
  seeds. Reject missing, duplicate, extra, misclassified or unknown keys.
  A changed `group` or `expected` must be rejected, not silently rescored.
- Derive correctness from `chosen == expected` and reject a conflicting flag.
  An unfamiliar nonempty chosen action counts as an incorrect choice, rather
  than disappearing from the denominator. Row order does not affect validation.

## Summary and comparison

Recompute every dataset's `correct`, `total`, `unknown_budget_cases`,
`unknown_budget_false_order_intentions`, `by_age` and `by_group`. Age keys are
strings; age/group values contain `correct` and `total`. Unknown-budget groups
must be declared for each dataset and exist in its frozen probes. Count false
order intentions using `order_action`, without trusting stored group labels.
Require exact type-sensitive equality with the supplied summary, including
denominators and nested counts. Boolean/float counters are not integer counters.

Compare validated maps by their complete keys, never by a shorter positional
iteration. In the buyer experiment the frozen product contains `567` old and
`216` fresh rows. These numbers are experiment inputs, not validator constants.
The zero-regression and non-increased-budget gates remain unchanged. Fresh
controls remain report-only; no score confers professional qualification.

Tests must cover missing/duplicated rows, all old rows relabelled as fresh,
metadata/answer tampering, incorrect flags, dishonest budget summaries,
denominator/count-type errors and a valid reordered artifact. Fixtures contain
synthetic data only. Personal corpora and local settings stay outside commits.
