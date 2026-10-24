## Abstract

Russian version: [NOWA_Body_Layer_Phase1_AsBuilt_MCP_API.ru.md](NOWA_Body_Layer_Phase1_AsBuilt_MCP_API.ru.md)

The document of 18 August 2026 is the record of the Phase 1 implementation and the MCP integration contract. The delivery includes the organ description `MCPCapability`, a per-agent registry indexed by action type, the sensory encoder, a seeder with an obligatory `ACTION` event, an abstract `MotorAdapter` and `ProcurementBodyMotorAdapter`, the approval gate, hard constraints, the feedback loop, `MockMCPClient`, the `run_cycle` and `tick` cycle together with `SleepScheduler`, the role `nowa_roles/procurement/`, and the laboratory interface. The package `nowa_body` does not import `nowa_sandbox`. A note of 24 August 2026 states that the required `MotorAdapter` extension point is replaced by the path of canonical A(t) and `SchemaBinder`; the tool identifier, the envelopes, and `ApprovalGate` of the present document remain in force. The cognitive call `agent.step(..., decision_only=True)` does not know the protocol, and the core does not import a protocol SDK.

Invariants B1–B9 record the boundary as implemented. The adapter does not call hippocampal activation, the selector, or the agent step. Every seed and feedback path contains exactly one `ACTION` event and is built by reassignment. The waking cycle calls `decision_only=True` when the signature allows it. The only point of write execution is `ApprovalGate`. The combination of `HIGH_WRITE` or `IRREVERSIBLE` with approval required set to false yields `HardConstraintViolation` inside `route()`. An episode is written after a known outcome of automatic execution or of a human decision; `wait_and_monitor` and an empty proposal do not add to the store. Sensor rate is separate from step rate: the host calls `tick()` at about 1 Hz, sensors refresh by default once every 300 s, and the transport client is held by the gate, not by the runtime. The closed question about process S is stated as follows: pressure is read by `get_sleep_pressure()` from `WakefulnessState._wakefulness`, the agent attribute is named `wakefulness`, growth proceeds through `update_waking()`, and the scheduler accepts both attribute names. The intention summary remains the machine string of `_summarize()`.

The transport contract is a function `(tool_id, params) -> dict` with an obligatory `status` field. The identifier has the form `mcp__<server>__<tool_name>` and is not renamed after episodes exist, because feedback writes it into the hippocampus. Success with statuses `accepted`, `success`, and `ok` yields the token `result:success` and an affective shift of valence +0.4, arousal 0.2, and trust 0.3. Refusal with statuses `rejected`, `failed`, and `error` yields `result:failure` and a shift of valence −0.4, arousal 0.5, and stress 0.4. Anything else, including a missing field, is `unknown` with an empty affective map. Transport exceptions are normalised into an error envelope and are not propagated into the cycle, except a hard-constraint violation before execution. The table of divergences keeps the next phase from returning the implementation to contradictory pseudocode: in particular, capability initialisation does not itself force approval, and the violation is caught at the gate.

---

# NOWA Body Layer — As-Built Phase 1 and the MCP Integration Contract

**Version:** 1.0  
**Status:** Implementation record + integration contract  
**Date:** 2026-08-18  
**Addendum (2026-08-24):** MotorAdapter as a required extension point is
superseded. Canonical A(t) + SchemaBinder path is in
`NOWA_Body_Layer_AffectiveSpace_Body_Addendum.md` and
`Docs/spec_affective_space_platform_body.md`. `tool_id`, envelopes, and
ApprovalGate in this document still apply.

**Base documents:**
- `NOWA_Virtual_Employees_Architecture_Spec.md` (sections 0–6)
- `NOWA_Body_Layer_Phase1_Spec.md` v1.0
- `NOWA_Body_Layer_Phase1_Patch_v1.1.md`
**Code:** `Demo/Virtual company/src/nowa_body/`, `nowa_roles/procurement/`
**Purpose of this document:** to record *how the system is actually implemented*, and to give
a stable contract for MCP tools for the next integrations (1C, email, CRM,
a payment gateway) with a sovereign NOWA agent. Divergences from the pseudocode
of the original specifications are marked **As-built**.

---

## 0. What this delivery contains (in brief)

A universal “body” layer is implemented: an MCP tool is described as an organ of the agent
(`MCPCapability`), registered in a per-agent registry, read through the sensory
adapter, and executed only through `ApprovalGate`. The cognitive circuit
(`agent.step(..., decision_only=True)`) does not know about MCP.

| Area | Result |
|---|---|
| Capability layer | `mcp_capability.py`, `risk_classifier.py`, `tool_registry.py` with an `action_type` index |
| Sensory + seed | `business_event_encoder.py`, `business_hippocampus_seeder.py` (lesson 2: an obligatory ACTION event) |
| Motor | abstract `MotorAdapter` + `ProcurementBodyMotorAdapter` |
| Governance | `approval_gate.py`, `hard_constraints.py`, `feedback_loop.py` |
| Transport for tests | `mock_mcp.py` — READ + WRITE with no network |
| Runtime | `run_cycle()` + `tick()` (sensor cache) + `SleepScheduler` |
| Role | `nowa_roles/procurement/` (corpus, classifier, motor) |
| Laboratory | `nowa_body/gui_app.py`, `run_body_gui.bat` |
| Isolation | `nowa_body` does **not** import `nowa_sandbox` |

**Q-Phase1-1a (closed):** Process S in the core is `WakefulnessState._wakefulness`,
read by `get_sleep_pressure()`. The agent attribute is `wakefulness` (not
`wakefulness_state`). Pressure grows only through `update_waking()`, not from
a tick counter. `SleepScheduler` reads both attribute names.

**Q-Phase1-2 (implemented):** the host calls `tick()` at about 1 Hz; sensors are refreshed
once per `sensor_refresh_interval_s` (300 s by default).

**Q-Phase1-3:** `intent_summary` remains the machine string of `_summarize()`;
natural-language generation for the UI is deferred.

---

## 1. Principles that an integration is not permitted to violate

Inherited without change:

1. The agent is a sovereign unit. The tool registry is **per-agent**; the MCP transport
   may be shared.
2. Learning occurs only during sleep. The waking cycle of the body uses
   `agent.step(..., decision_only=True)` and writes an episode **after** a known
   outcome.
   Since #13: waking outcomes go to the labile tier, stable values change only in `Agent.sleep()`; the employee host passes `dt` ([issue-13-demo-virtual-company.en.md](../../../Docs/specs/issue-13-demo-virtual-company.en.md)).
3. Money, risk, and approval lie outside the cognitive circuit. The agent cannot
   “change its mind” about `ApprovalGate`.
4. MCP tools are organs of the agent, not “integrations”. The NOWA core does not import
   an MCP SDK.

Body invariants (as-built B1–B9):

| # | Rule |
|---|---|
| **B1** | `MotorAdapter.resolve()` does not call `hippocampus.activate`, the selector, or `agent.step` |
| **B2** | Every seed and feedback Path contains exactly one `EventType.ACTION` |
| **B3** | A `Path` is built by reassignment (`path = path.add_event(...)`) |
| **B4** | The runtime calls only `decision_only=True` (when the signature allows it) |
| **B5** | The only WRITE-execute point is `ApprovalGate` (`mcp_executor`) |
| **B6** | `HIGH_WRITE` / `IRREVERSIBLE` + `requires_approval=False` yields `HardConstraintViolation` in `route()` |
| **B7** | Feedback follows a known outcome: auto-execute (`record.executed`) or a human `decide()` |
| **B8** | `wait_and_monitor` or an empty `ProposedAction` does not call `hippocampus.store` |
| **B9** | The sensor rate is decoupled from the rate of `agent.step` |

---

## 2. Boundary: who does what

```
Host (scheduler / GUI / a future MCP client)
    │  1. polls READ tools (infrequently)
    │  2. assembles observations
    │  3. calls runtime.tick(sensor_fetcher)  or  run_cycle(observations)
    ▼
nowa_body.BusinessAgentRuntime
    │  encode_tool_result → context_events
    │  agent.step(context_events, decision_only=True) → action_type
    │  MotorAdapter.resolve → ProposedAction | None
    │  ApprovalGate.route
    │     ├── requires_approval=False → mcp_executor(tool_id, params)
    │     └── otherwise → pending_queue (a human)
    ▼
mcp_executor: (tool_id: str, params: dict) -> dict
    │  As-built: MockMCPClient.execute
    │  Phase 3: a real MCP transport (one per process, many agents)
    ▼
external MCP server (1C, email, …)
```

**As-built:** `BusinessAgentRuntime` does **not** store an MCP client. The reference to
the transport lives only in `ApprovalGate.mcp_executor`. READ polling is the duty
of the host (`sensor_fetcher`).

---

## 3. MCP Tools API contract (the core of the integration)

This section is the source of truth for attaching a new MCP server to NOWA.
The Phase 1 implementation closes the contract through `MockMCPClient`; Phase 3
replaces only the transport, not the capability fields and not the shape of the result dict.

### 3.1 Tool identifier (`tool_id`)

A stable string, unique within an agent (and preferably globally
within the company).

**Recommended format:**

```
mcp__<server>__<tool_name>
```

Examples:

| tool_id | server_name | meaning |
|---|---|---|
| `mcp__1c__get_stock_levels` | `1c_erp` | stock sensor |
| `mcp__1c__create_purchase_order` | `1c_erp` | order muscle |
| `mcp__email__send` | `email` | letter muscle |

Rules:

- `tool_id` is the registry key and the argument of `mcp_executor`.
- The segment after the last `__` is used by the fallback event
  classifier (`encode_tool_result` without a role classifier).
- Do not rename `tool_id` after episodes exist: feedback writes
  `action:<tool_id>` into the hippocampus.

### 3.2 Transport call (the only I/O point)

```text
mcp_executor(tool_id: str, params: dict) -> dict
```

This is the **only** signature that the body knows.

| Argument | Type | Requirement |
|---|---|---|
| `tool_id` | `str` | Exact match with `MCPCapability.tool_id` |
| `params` | `dict` | A JSON-compatible object (string keys). An empty `{}` is admissible for a READ with no filters |

**The return is always a `dict`.** As-built, `MockMCPClient.execute` and
`ApprovalGate._invoke_executor` normalise failures into a dict and **do not propagate**
an exception into the runtime (except `HardConstraintViolation` before execute).

An integrator of a real MCP is obliged to:

1. Serialise an MCP JSON-RPC or SDK result into a `dict`.
2. Catch timeout and network failure and return an error envelope (see 3.3).
3. Not return `None`, a list, or a str at the top level.

### 3.3 Result envelope (obligatory field `status`)

The body **does not parse** the domain business schema of 1C inside the outcome encoder. The outcome
of an action is read as follows:

```text
status = str(result["status"]).strip().lower()
```

| Class | Values of `status` (as-built) | Episode tokens | Affect |
|---|---|---|---|
| Success | `accepted`, `success`, `ok` | `result:success` | valence +0.4, arousal 0.2, trust 0.3 |
| Refusal | `rejected`, `failed`, `error` | `result:failure` | valence −0.4, arousal 0.5, stress 0.4 |
| Other | any other value, including a missing field, which becomes `unknown` | `result:unknown` | `{}` |

Recommended canonical envelope for **any** tool:

```json
{
  "status": "ok",
  "reason": null,
  "...": "domain fields"
}
```

Transport errors (as-built normalisation):

| Situation | Envelope |
|---|---|
| Unknown `tool_id` | `{"status": "error", "reason": "unknown_tool:<id>"}` |
| `TimeoutError` | `{"status": "error", "reason": "timeout:<exc>"}` |
| Any other tool exception | `{"status": "error", "reason": "tool_error:<exc>"}` |
| A non-dict from the tool | `{"status": "error", "reason": "non_dict_result", "value": ...}` |
| An executor exception in the gate | `{"status": "error", "reason": "executor_error:<exc>"}` |

**Rule for the integrator:** do not raise from the executor in Phase 3 if an
envelope can be returned. Then `apply_feedback_to_agent` always sees `status`, and
the agent learns from the real outcome rather than from a host crash.

Domain fields (stock levels, order id, letter text) live **beside** `status`,
not in its place.

### 3.4 READ and WRITE

| Class | `CapabilityRisk` | Who calls | When |
|---|---|---|---|
| Sensor | `READ_ONLY` | **the host** (`sensor_fetcher`) | once per `sensor_refresh_interval_s`, or on a webhook |
| Muscle | any value other than `READ_ONLY` | **only** `ApprovalGate` | after `MotorAdapter.resolve` and, when required, a human |

Sensory calls do **not** pass through `ApprovalGate` in the current runtime: the host
polls READ itself and places the payload in `observations["tool_results"]`.
This separation is deliberate: approval is a barrier for money and for mutation of the world, not a barrier
for sight.

`requires_approval=False` for `READ_ONLY` is a normal Stage 2 configuration.

`requires_approval=False` for `HIGH_WRITE` / `IRREVERSIBLE` is **forbidden**
(B6). For `MEDIUM_WRITE` on Stage 2 the default is `True`.

### 3.5 `MCPCapability` — the passport of an organ

File: `nowa_body/mcp_capability.py`.

```text
MCPCapability
  tool_id:                str              # §3.1
  server_name:            str              # logical server name, not a URL
  display_name:           str              # for a human / the UI
  description:            str              # for the risk heuristic and the operator
  risk_level:             CapabilityRisk
  domain_tags:            List[str]        # ["procurement"], ["finance"], …
  input_schema:           Dict[str, Any]   # JSON Schema (recommended)
  output_schema:          Dict[str, Any]   # JSON Schema (recommended)
  requires_approval:      bool = True
  cost_impact_estimate:   Optional[str]    # "none"|"low"|"medium"|"high"
  max_autonomous_value:   Optional[float]  # Stage 3 autonomy threshold
  action_types:           List[str]        # ActionSelector labels
```

**As-built difference from the parent specification:** `__post_init__` does **not** rewrite
`requires_approval=True` for WRITE. An invalid combination can be represented as
data and is caught by `assert_stage2_invariant` in `ApprovalGate.route`; otherwise
the test “HIGH_WRITE cannot be bypassed” would be dead code.

#### 3.5.1 `action_types` — the bridge from brain to muscle

NOWA selects a **strategy label**, not a `tool_id`.

Examples:

| action_type (brain) | typical tool_id (body) |
|---|---|
| `place_order_reliable_supplier` | `mcp__1c__create_purchase_order` |
| `urgent_reorder` | the same WRITE tool, different params |
| `notify_supplier_urgent` | `mcp__email__send` |
| `wait_and_monitor` | **no tool** — the motor returns `None` |

One tool may cover several `action_types`. Several tools for one
`action_type` are admissible: `MotorAdapter` selects the **lexicographically
smallest** `tool_id`. A role with several equivalent tools must
prioritise by registration or by distinct `action_types`, and must not rely
on chance.

`wait_and_monitor` is **not** registered as an `action_type` of a WRITE tool.

#### 3.5.2 `CapabilityRisk`

| Enum value | string | meaning | Stage 2 |
|---|---|---|---|
| `READ_ONLY` | `read_only` | reading the world | usually without approval |
| `LOW_WRITE` | `low_write` | a draft, not sent | approval by flag |
| `MEDIUM_WRITE` | `medium_write` | a letter, a request, a document | approval by default |
| `HIGH_WRITE` | `high_write` | money, a contract price | approval **always** |
| `IRREVERSIBLE` | `irreversible` | deletion, a final deal | approval **always** |

### 3.6 Risk heuristic (default only)

`classify_risk_heuristic(tool_name, description="") -> CapabilityRisk`

Order: IRREVERSIBLE, then HIGH, then MEDIUM, then LOW, then READ. An unknown pattern yields
`HIGH_WRITE` (fail-safe). The name is examined first, then the description.

A HIGH or IRREVERSIBLE tool classified by the heuristic alone must **not**
be given to an agent without human review.

Key substrings (as-built):

- READ: `get_`, `list_`, `search_`, `read_`, `fetch_`, `query_`, `check_`, `view_`
- LOW: `draft_`, `prepare_`, `compose_`, `generate_document_`
- MEDIUM: `send_`, `create_order_`, `submit_`, `post_`, `update_`
- HIGH: `pay_`, `transfer_`, `approve_payment_`, `sign_contract_`, `change_price_`
- IRREVERSIBLE: `delete_`, `cancel_contract_`, `terminate_`, `revoke_`

`register_from_mcp_discovery` in Phase 1 raises `NotImplementedError`. Phase 3:
discovery of MCP tools, then the heuristic, then **manual confirmation**, then `register()`.

### 3.7 Registry: a sovereign slice, a shared transport

```text
MCPToolRegistry(agent_id)
  register(capability)
  get(tool_id) -> Optional[MCPCapability]
  list_all() / list_by_risk / list_by_domain
  sensory_capabilities()   # READ_ONLY only
  motor_capabilities()     # everything that is not READ_ONLY
  capabilities_for_action(action_type) -> List[MCPCapability]
```

A repeated `register` with the same `tool_id` replaces the passport and rebuilds
the `action_type` index.

Two agents on one 1C server:

```
shared:   MCP transport / MockMCPClient
agent_A:  registry {get_stock_levels, create_purchase_order}
agent_B:  registry {get_invoices, post_payment}
```

Visibility is set by `register()`, not by a network ACL of the transport (an ACL is an additional
protection, not a substitute for sovereignty).

### 3.8 Input and output JSON Schema

`input_schema` and `output_schema` are **not validated** automatically in Phase 1.
For Phase 3 the integrator **must** fill them at registration: they are the contract
for MotorAdapter and for the human in the approval UI.

Recommended profile: JSON Schema draft-07, `type: object`, with no `$ref` to
an external URL.

The role’s MotorAdapter builds `tool_params` so that they satisfy
`input_schema`. The gate passes params to the executor **as they are** (after an optional
human modification).

### 3.9 Observation snapshot (`observations`) — the runtime input

The host assembles a dict **before** `run_cycle`, or inside `sensor_fetcher` for `tick()`.

Canonical form (as-built; the procurement role understands both layers):

```json
{
  "agent_id": "buyer_001",
  "affect_snapshot": {},
  "stock": { "<product_id>": { "...stock fields..." } },
  "suppliers": { "<supplier_id>": { "...supplier fields..." } },
  "budget": { "remaining": 8000.0, "utilization_ratio": 0.35 },
  "tool_results": {
    "mcp__1c__get_stock_levels": { "status": "ok", "stock": { } },
    "mcp__1c__get_suppliers": { "status": "ok", "suppliers": { } },
    "mcp__1c__get_budget": { "status": "ok", "remaining": 8000.0, "utilization_ratio": 0.35 }
  }
}
```

Rules:

- `tool_results`: a map `tool_id → envelope` (§3.3). The runtime encodes **only**
  this map into `context_events`. An empty map yields the token `quiet_period`.
- The top-level keys `stock`, `suppliers`, and `budget` are the normalised view for
  `ProcurementBodyMotorAdapter`. If they are absent, the adapter tries to extract
  nested values from `tool_results` by needles in `tool_id` (`stock`, `supplier`,
  `budget`) and by the keys `stock|products|stock_levels`, `suppliers|supplier_directory`.
- `agent_id` is copied into `ProposedAction.agent_id`.
- `affect_snapshot` is copied into `ProposedAction.affective_context` (it is not
  injected into `affective_space` at the solve stage).

For a new role: either place the normalised keys, or teach its own MotorAdapter
to read its own keys from `tool_results`. The encoder of the agent’s world depends only on
`tool_results` and `event_classifier`.

### 3.10 Sensory adapter: an MCP result becomes `context_events`

`BusinessEventEncoder.encode_tool_result(tool_id, result, event_classifier=None)`

1. If an `event_classifier(tool_id, result) -> List[str]` is passed and it returned
   a non-empty list of event names, those names are used.
2. Otherwise the event name is the last segment of `tool_id` after `__`.
3. For each name: the tokens `event:<name>`, plus valence, arousal, and domain from
   `affective_mapping` when the name is present in the map.

The classifier is **role-specific**. Procurement: `classify_procurement_events`
(stock below the reorder point yields `stock_critical_low`, a defaulted supplier yields `supplier_defaulted`,
and so on). Accounting will receive its own module. The universal encoder does not know 1C.

`encode_action_outcome(action_type, tool_result)` looks **only** at `status`
(§3.3). `action_type` is reserved for role encoders; as-built it is not
used. The ACTION event in the Path is added by the **caller** (`feedback_loop`):
`action:<proposed_action.tool_id>`.

### 3.11 Motor adapter: ActionIntent becomes `ProposedAction`

`ProposedAction` (not yet an MCP call):

| Field | Meaning |
|---|---|
| `action_id` | UUID, the key of the approval queue |
| `agent_id` | who proposed it |
| `tool_id` | which organ to call |
| `tool_params` | arguments of `mcp_executor` |
| `risk_level` | a copy from the capability |
| `requires_approval` | a copy from the capability |
| `intent_summary` | a string for the log and for a future UI |
| `affective_context` | the snapshot at the moment of the decision |
| `estimated_cost_impact` | optional float |

`resolve()` never raises: garbage observations yield `None`.
`wait_and_monitor`, or an unknown action_type with no capability, yields `None`.

The base `_build_params` raises `NotImplementedError` (caught, and the result is `None`).
A role is obliged to implement the assembly of params.

### 3.12 ApprovalGate: the WRITE route

```text
route(proposed) -> ApprovalRecord
decide(action_id, decision, decided_by, rejection_reason?, modified_params?) -> ApprovalRecord
expire_stale() -> List[ApprovalRecord]
```

`ApprovalStatus`: `pending | approved | rejected | modified | expired`.

Behaviour of `route`:

1. Assemble the capability: lookup by `tool_id` **or** the fields of `ProposedAction`.
2. Take the **more dangerous** risk from the lookup and from the proposal; `requires_approval`
   is the OR of the two flags (the proposal cannot “lower” the registry flag).
3. `assert_stage2_invariant`.
4. If approval is not required, call `mcp_executor` immediately, with `executed=True` and
   `decided_by="system:read_only_auto"`.
5. Otherwise write into `pending_queue`, and optionally call `notification_channel(record)`.

`decide`:

- `APPROVED` or `MODIFIED` executes, with `executed=True`.
- `MODIFIED` merges `modified_params` into `tool_params`.
- `REJECTED` does not execute, with `executed=False`.
- A missing id in the queue raises `KeyError`.

The runtime method `complete_approval`, after `decide`, calls feedback if the status
is no longer `PENDING` (including reject: the outcome is a human decision).

Queue timeout: `approval_timeout_hours` (default 48), `expire_stale()`.
An expired record is not executed; the as-built reward is −0.2.

### 3.13 Feedback into the hippocampus (after the outcome)

`approval_to_reward`:

| status | reward |
|---|---|
| APPROVED | +1.0 |
| MODIFIED | +0.4 |
| REJECTED | −1.0 |
| EXPIRED | −0.2 |
| otherwise | 0.0 |

Path: CONTEXT tokens from `encode_action_outcome`, plus one ACTION
`action:<tool_id>`, plus a CONSEQUENCE `approved` if reward is greater than 0, otherwise `rejected`.

Affect: `affective_space.step(inputs=...)`, when it is present.

### 3.14 Procedure for attaching a new MCP server (Phase 3 checklist)

1. Obtain the list of tools from the server (MCP `tools/list`).
2. For each tool:
   - assign a stable `tool_id` (`mcp__<server>__<name>`);
   - fill `input_schema` and `output_schema` from the MCP `inputSchema`;
   - run `classify_risk_heuristic`, **then** a human confirms
     `risk_level` and `requires_approval`;
   - assign `action_types` from the lexicon of the role (not blindly from the tool name);
   - set `domain_tags`.
3. Register the **slice** in the `MCPToolRegistry` of the particular agent.
4. Implement `mcp_executor` as a thin SDK wrapper: always a `dict` plus `status`.
5. Host: READ tools in `sensor_fetcher` with an interval other than 1 Hz.
6. Role: an `event_classifier` and a subclass of `MotorAdapter._build_params`.
7. Run: a pending HIGH or MEDIUM write; a B6 probe; a timeout envelope;
   `wait_and_monitor` writes no episodes.

---

## 4. Reference: tools of the laboratory role “buyer” (MockMCP)

This is **not** the final 1C contract. It is the reference form that a 1C adapter must
repeat or map explicitly.

### 4.1 `mcp__1c__get_stock_levels` — sensor

| | |
|---|---|
| risk | `READ_ONLY`, `requires_approval=False` |
| action_types | `[]` (the host, not the brain) |
| params | `{}` (filters are future work) |

**Output (as-built laboratory):**

```json
{
  "status": "ok",
  "stock": {
    "sku_a": {
      "quantity": 0.0,
      "reorder_point": 40.0,
      "below_reorder_point": true,
      "base_demand_per_day": 1.5,
      "projected_quantity": 0.0
    }
  }
}
```

Fields understood by `ProcurementBodyMotorAdapter` (any subset):

- quantity: `quantity`, plus inbound `inbound` / `inbound_quantity`, or
  directly `projected` / `projected_quantity`
- reorder point: `reorder_point`, `replenishment_point`, and the flags
  `below_reorder_point` / `below_replenishment_point` /
  `projected_below_replenishment_point`
- demand: `base_demand_per_day`, so that qty equals demand times 30 days

Classifier: any SKU below the point yields the event `stock_critical_low`.

### 4.2 `mcp__1c__get_suppliers` — sensor

```json
{
  "status": "ok",
  "suppliers": {
    "acme": {
      "reliability": 0.95,
      "unit_price": 8.0,
      "lead_time_days": 3,
      "reputation": 0.9,
      "is_defaulted": false,
      "status": "active",
      "offers": {
        "sku_a": {
          "unit_price": 8.0,
          "reliability": 0.95,
          "lead_time_days": 3
        }
      }
    }
  }
}
```

Synonyms read by the motor:

- price: `unit_price` | `base_price` | `price` | `base_price_multiplier`
- lead time: `lead_time_days` | `lead_time`
- reliability: `reliability` | `reliability_score`
- offers: `offers` | `product_offers` (a dict, or a list with `product_id`)
- unavailable: `is_defaulted=true`, `available=false`, `status` in
  `{unavailable, defaulted, inactive}`

`is_defaulted`, or a status of defaulted, yields the event `supplier_defaulted`.

### 4.3 `mcp__1c__get_budget` — sensor

```json
{
  "status": "ok",
  "remaining": 8000.0,
  "utilization_ratio": 0.35
}
```

The motor caps qty at `floor(remaining / unit_price, 1 decimal place)`.
`remaining <= 0` or `utilization_ratio > 0.9` yields `budget_exceeded`.

### 4.4 `mcp__1c__create_purchase_order` — muscle

| | |
|---|---|
| risk | `MEDIUM_WRITE` |
| requires_approval | `True` on Stage 2 (the laboratory auto-execute checkbox is for debugging only, and resets the session) |
| action_types | `place_order_reliable_supplier`, `place_order_cheap_supplier`, `urgent_reorder`, `diversify_supplier` |

**Input (`tool_params`, as-built):**

```json
{
  "supplier_id": "acme",
  "product_id": "sku_a",
  "qty": 45.0,
  "strategy": "place_order_reliable_supplier",
  "confidence": 0.95
}
```

`strategy` and `confidence` are decision metadata; 1C may ignore them,
but they are useful in an audit.

**Output:**

```json
{
  "status": "accepted",
  "params": { "supplier_id": "acme", "product_id": "sku_a", "qty": 45.0 }
}
```

The laboratory also emulates `rejected`, `timeout`, and `error` with the same envelope
(timeout yields `status=error`, and `reason` contains `timeout:`).

Supplier-selection strategies (the body, not the brain):

| action_type | rule |
|---|---|
| `place_order_reliable_supplier` | maximum reliability |
| `place_order_cheap_supplier` | minimum price (fallback: minimum reputation) |
| `urgent_reorder` | minimum lead_time (fallback: maximum reputation) |
| `diversify_supplier` | minimum mentions of `supplier:<id>` in `hippocampus.experiences` (read-only) |

If no SKU is below the reorder point, no supplier is available, or qty after the cap is 0, `resolve`
returns `None` (a tick with no WRITE).

---

## 5. Host runtime API

### 5.1 `BusinessAgentRuntime`

```text
tick(sensor_fetcher, *, now=None) -> dict
run_cycle(observations, *, now=None) -> dict
complete_approval(action_id, decision, decided_by="human",
                  rejection_reason=None, modified_params=None) -> ApprovalRecord
```

`tick`: if the sensor interval has elapsed, call `sensor_fetcher()`; otherwise use the cache.
The result key is `sensor_refreshed: bool`.

`run_cycle`: a pure pass over a ready snapshot (tests, a sandbox).

Shared result keys:

| Key | When |
|---|---|
| `action_type` | always |
| `context_events` | always |
| `proposed` | a `ProposedAction` or `None` |
| `approval_status` | if there was a proposal |
| `executed` | if there was a proposal |
| `record` | an `ApprovalRecord` if there was a proposal |
| `slept` | bool |
| `sleep_reason` | `"circadian"` or `"fatigue"` or `""` |
| `sensor_refreshed` | only after `tick()` |

Sleep: `SleepScheduler` (hour window 02:00–05:00 by default, Process S threshold
0.85, anti-thrash `min_ticks_between_sleep` default 3600). After sleep,
`mark_slept()`. The laboratory host may set `min_ticks=0`.

`simulated_tick_seconds`: an explicit `update_waking(elapsed)` for tests; in a live
1 Hz loop, wall-clock time inside `Agent.step` plus a no-op second call is enough.

### 5.2 Call into the NOWA core

```text
agent.step(context_events: List[str], decision_only=True) -> str | intent
```

The runtime extracts a string from a `str`, or from the attributes `action_type`, `action`, `label`, or `name`.
Otherwise it uses `wait_and_monitor`.

An episode is **not** written into the hippocampus from `step()` (`decision_only`). The body writes
after MCP or after a human.

---

## 6. As-built module map

```
src/nowa_body/          # universal body, without nowa_sandbox
  mcp_capability.py
  risk_classifier.py
  tool_registry.py
  business_event_encoder.py
  business_hippocampus_seeder.py
  motor_adapter.py
  approval_gate.py
  hard_constraints.py
  feedback_loop.py
  mock_mcp.py
  sleep_scheduler.py
  runtime.py
  lab_session.py        # headless laboratory (not part of __init__)
  gui_app.py / gui_i18n.py
src/nowa_roles/procurement/
  motor_adapter.py      # ProcurementBodyMotorAdapter
  seed_corpus.py
  event_classifier.py
```

The public package import (`nowa_body.__init__`) does not pull in the GUI or the roles.

Laboratory launch: `Demo/Virtual company/run_body_gui.bat`.

---

## 7. As-built divergences from the pseudocode of the original specifications

| Topic | Specification v1.0 / parent | As-built |
|---|---|---|
| `MCPCapability.__post_init__` | forces approval on MEDIUM and above | does not force it; B6 is caught at the gate |
| `ApprovalGate` lookup | proposed fields only | registry lookup, plus max(risk), plus OR(approval) |
| Location of packages | `nowa_body/tests/` | `Demo/Virtual company/tests/` (as for the sandbox) |
| `nowa_governance/*` | separate packages | inside `nowa_body` |
| `register_from_mcp_discovery` | “under the SDK” | `NotImplementedError` until Phase 3 |
| Executor exceptions | not specified | always normalised to `{status: error}` |
| Feedback on reject | B7 “executed only” versus parent 6.4 | `route`: executed only; `complete_approval`: any terminal decide |
| Sleep | an open question | `SleepScheduler` + `tick()` |

These rows are a checklist, so that Phase 3 does not “correct” the as-built implementation back into
contradictory pseudocode.

---

## 8. Minimal integration example (host pseudocode)

```python
registry = MCPToolRegistry(agent_id="buyer_001")
registry.register(stock_cap)          # READ_ONLY
registry.register(order_cap)          # MEDIUM_WRITE + action_types

def mcp_executor(tool_id: str, params: dict) -> dict:
    # SDK call → always a dict with a status field
    ...

gate = ApprovalGate(
    mcp_executor=mcp_executor,
    capability_lookup=registry.get,
    notification_channel=notify_human,  # Slack/UI
)

runtime = BusinessAgentRuntime(
    agent=nowa_agent,
    tool_registry=registry,
    motor_adapter=ProcurementBodyMotorAdapter(registry),
    approval_gate=gate,
    encoder=BusinessEventEncoder(affective_mapping),
    event_classifier=classify_procurement_events,
    sensor_refresh_interval_s=300.0,
)

def fetch_sensors() -> dict:
    stock = mcp_executor("mcp__1c__get_stock_levels", {})
    suppliers = mcp_executor("mcp__1c__get_suppliers", {})
    budget = mcp_executor("mcp__1c__get_budget", {})
    return {
        "agent_id": "buyer_001",
        "stock": stock.get("stock", {}),
        "suppliers": suppliers.get("suppliers", {}),
        "budget": budget,
        "tool_results": {
            "mcp__1c__get_stock_levels": stock,
            "mcp__1c__get_suppliers": suppliers,
            "mcp__1c__get_budget": budget,
        },
    }

# about 1 Hz
runtime.tick(fetch_sensors)

# when a human pressed Approve in the UI
runtime.complete_approval(action_id, ApprovalStatus.APPROVED, decided_by="ivan")
```

---

## 9. Open for later phases

| ID | Topic |
|---|---|
| Phase 2 | a human approval UI (Slack/email); natural-language generation of `intent_summary` (Q-Phase1-3) |
| Phase 3 | a real MCP SDK inside `mcp_executor`; `register_from_mcp_discovery` plus human review |
| Phase 3 | validation of `tool_params` against `input_schema` before execute |
| Roles | sales and accounting: their own seed corpus, classifier, and MotorAdapter |
| Security | a network ACL for MCP in addition to the per-agent registry |

---

*As-built Phase 1 and MCP Tools API contract v1.0. Ready as an input document
for integrations with a NOWA agent. Code in `nowa_body` takes priority where it diverges
from the pseudocode of Phase 1 Specification v1.0.*
