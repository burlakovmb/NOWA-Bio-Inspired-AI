# Body layer — business limits declared by a role

Russian: [NOWA_Business_Limits.ru.md](NOWA_Business_Limits.ru.md)

Module: `Demo/Virtual company/src/nowa_body/business_limits.py` (stdlib only), wired into the employee's `BusinessAgentRuntime` (`nowa_body/runtime.py`, a subclass of the platform runtime).
Related: [NOWA_Body_Lessons.en.md](NOWA_Body_Lessons.en.md) (the "wait" lesson goes through `teach`).

The core (`src/`, including the platform body layer `mcp_body`) is not changed.

---

## 1. Problem

A role can have rules that a call must never break, such as "do not spend more than is available". If the only guard is what the mind has learned, the guard is as good as the training: an agent that has learned to act will act while the amount is exhausted, and the approval gate becomes the only defence. Learning such a rule as intuition is also the wrong tier: a rule does not need to be rediscovered on every shortage.

`hard_constraints` are architectural invariants and cannot be configured away. Business limits are the other kind: declared per role in `config.yaml`, read from the world each cycle, enforced by the body.

## 2. Contract

A role lists limits under `business_limits`:

```yaml
business_limits:
- name: quota                       # any name; reported back to the host
  tools: [mcp__desk__reserve_slot]  # WRITE tools it guards; empty = every WRITE
  available: results.mcp__desk__get_quota.left      # world-state path to the amount left
  cost:                              # optional: price the call
    qty_param: count                 # the bound parameter that is a quantity
    unit_price: results.mcp__desk__get_prices.slots.{slot_id}.price  # {param} placeholders
  on_exceed: clip                    # clip | block (default block)
  min_qty: 1                         # smallest quantity worth sending after a clip
  lesson_reward: 0.6                 # >0: first block of a shortage files "wait"
  consequence: quota_kept            # consequence name of that lesson
```

The module knows only "an amount at a world path" and, optionally, "a quantity parameter times a unit price at a world path". No domain field names are built in; the role supplies every path.

## 3. Check (`check_limit`, `apply_limits`)

For a bound call of a guarded tool, after `SchemaBinder` and before `ApprovalGate.route`:

| Situation | Verdict | Reason |
| --- | --- | --- |
| Amount cannot be read | blocked | `limit_unknown` |
| Amount ≤ 0 | blocked | `nothing_left` |
| Call cannot be priced (no quantity, no price, price ≤ 0) | ok | — (only "something is left" is checked) |
| Cost ≤ amount | ok | — |
| Cost > amount, `on_exceed: clip`, `floor(amount / price) ≥ min_qty` | clipped (quantity reduced) | `clipped_to_available` |
| Otherwise | blocked | `over_available` |

Limits run in config order; a clip is seen by the next limit; the first block stops. The caller's params are never mutated. Malformed rows (no `available`) are skipped; an unknown `on_exceed` means `block`.

## 4. Runtime

`BusinessAgentRuntime(business_limits=..., limit_notifier=...)` accepts raw config rows or parsed limits.

- **Blocked:** the call never reaches the approval gate. The cycle result carries `limit_blocked`, `limit_reason`, `limit_episode_start`, `waited: True`.
- **Clipped:** the call goes on with the reduced quantity; the result carries `limit_clipped: [names]`.
- **Shortage episode.** The first block of a limit opens an episode: one lesson "wait" (`teach(context, wait_and_monitor, lesson_reward, consequence)`) if `lesson_reward > 0`, and one notice to the host (`limit_notifier({limit, reason, tool_id, params, available, cost, summary})`). Later blocks of the same episode are silent. The episode closes when a call passes the limit or the available amount grows above the amount at the first block. An unreadable limit (`limit_unknown`) opens no episode. A failing notifier does not break the cycle.

The lesson goes through the same path as approval feedback ([NOWA_Body_Lessons.en.md](NOWA_Body_Lessons.en.md)): a hippocampal episode and a labile tag; stable values change only in sleep.

Why one lesson per episode: a lesson per blocked tick (tens per shortage) tilts the mind toward waiting in every situation, including those where acting is right (measured on the Virtual company buyer: day-30 probe 82 with a lesson per block, 87 with one per episode, 5 seeds, core before #13).

## 5. Tests

`Demo/Virtual company/tests/test_body_business_limits.py` (domain-free: a reservation quota): every row of §3, parse defaults, limit order, clip seen by the next limit; runtime — the gate is not reached, one lesson and one notice per episode, a fitting call or a grown amount ends the episode, an unreadable limit opens none, a failing notifier, zero lesson reward, clipped call reported.

The Virtual company buyer declares its budget this way (`Demo/Virtual company/src/nowa_roles/procurement/config.yaml`; host notices become employee alerts) — tested in `test_business_limits.py`.

## 6. Out of scope

- Limits on READ tools; limits that are not "an amount and an optional unit price".
- Reserving the amount between the check and the external system's own accounting (the next read updates the world).
