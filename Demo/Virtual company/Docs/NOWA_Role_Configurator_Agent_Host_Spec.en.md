## Abstract

Russian version: [NOWA_Role_Configurator_Agent_Host_Spec.ru.md](NOWA_Role_Configurator_Agent_Host_Spec.ru.md)

The employee-host specification introduces a layer beside the role configurator and separates three entities. A role is job data in `nowa_roles/<role_id>/config.yaml`: servers, organs, risk, a seed, and an affective map; a role is not started. An employee is a named instance of a mind: the file `nowa_employees/<agent_id>/employee.yaml`, a list of role identifiers, its own rhythm, and a life cycle; the core's technical field remains `agent_id`, matching a lowercase Latin label of up to 48 characters. A session is a live runtime in the process memory while the graphical host is running; on stop, the mind is written to disk. Two employees with one role have two hippocampi, two vectors A(t), and two approval queues. A role dry run and the separate laboratory window are not an employee: the laboratory knows four hard-wired mock tools, whereas the procurement role already describes a live HTTP server `drivemcp` at `http://localhost/DriveDemo/hs/mcp`, to which write execution and sensor polling from the configurator are not yet directed.

Write parameters are assembled by `SchemaBinder`. Decision channels are write-tool identifiers and `wait_and_monitor`. The mind does not import the protocol. Sleep is the consolidation phase `sleep_cycle` and is set in wall-clock seconds separately from the tick interval; the card example is a tick of 1 s, sleep no more often than once per 3,600 s, a circadian window of hours 2–5, and a fatigue threshold of 0.85. Sleep does not follow from the fact of a tick. Role membership changes only in the `stopped` state; editing a role YAML while a session is running leaves the session with the snapshot from start and marks a stale-role plaque. Seeding runs only when memory is empty and is not repeated after a stop and a later start. An unavailable live transport at start moves the employee to `error` and is not replaced by a mock. Polling concerns only organs with `poll: true`; a write cannot carry that flag. Approval is visible on the card and as a pending count in the list. Badge states are stopped, starting, running, sleeping, awaiting approval, stopping, and error; awaiting approval does not stop ticks.

Constraints H1–H17 include a single write point through `ApprovalGate`, a prohibition on automatic execution of a high or irreversible write, `decision_only=True` on a waking tick, a prohibition on importing `nowa_sandbox`, a prohibition on adding axes to affective space, and a requirement that `mind.pkl` be written successfully for a normal stop. Several roles of one employee are folded by a union of organs keyed by `tool_id`; the same key at a different risk level is a configuration error, and one tool name on different servers yields two organs. Acceptance of this host version is performed on a mock: start, ticks, stop, restoration of the episode count, and independence of the sleep period from the number of ticks, including a tick of 60 s and a minimum sleep interval of 3,600 s. A live Drive run is assigned to the next manual step and is not part of the automated tests of this delivery. There is no limit on the number of employees or on the number of sessions running at once.

---

# NOWA Role Configurator — Employee Host (roles, then instance, then start/stop)

**Version:** 1.0  
**Status:** Ready for implementation — there are no open questions  
**Date:** 2026-08-27  
**Target user:** the same person as for the role configurator — someone who configures
organs and intuition without Python, and then starts a particular employee.
**End goal of this line:** a sovereign NOWA employee that reads and
changes data in information bases through MCP tools (including a 1C publication,
Drive, or any other `MCPTransport`). The host does not know what a “base” is — it
knows organs.

**Parent documents (do not rewrite them; only keep them consistent):**

- `NOWA_Role_Configurator_GUI_Spec.md` — the role GUI, invariants G1–G7
- `NOWA_Body_Layer_RoleConfig_Spec.md` — role YAML as data
- `NOWA_Body_Layer_AffectiveSpace_Body_Addendum.md` — SchemaBinder, not MotorAdapter
- `Docs/spec_affective_space_platform_body.md` — P1–P11, a tool is an organ
- `NOWA_Body_Layer_Phase1_AsBuilt_MCP_API.md` — `tool_id`, envelope, ApprovalGate
- `NOWA_Virtual_Employees_Architecture_Spec.md` — an employee is a sovereign unit
- `src/storage.py` — `AgentStorage.save_agent` / `load_agent` (the mind checkpoint)

**Principle of this specification:** the role configurator remains a thin visual layer
over `role_config.py`. The employee host is a *new* layer beside it, not inside
role validation. A role describes the work. An employee is an instance of a mind to which
that work has been assigned. Start and stop do not edit the role YAML.

The name in the UI and in this specification is **employee**. The technical identifier
remains `agent_id` (that is the name of the field in the NOWA core). The entity file is
`employee.yaml`.

---

## 0. Why this exists when Dry Run and Body Lab already exist

The configurator currently has two different “runs”, and neither is an
employee:

| What exists | What it actually is |
|---|---|
| The “Test run” tab | A one-shot `BodyLabSession` for *one* role, MockMCP, four hard-wired tools (`get_stock_levels` / `get_suppliers` / `get_budget` / `create_purchase_order`), simulated clocks, `force_action` |
| Body Lab GUI (`run_body_gui.bat`) | The same laboratory, a separate window, warehouse scenarios |

What is missing:

- an entity “this employee”, with a name, a memory, and assigned roles;
- assignment of **several** roles to one mind;
- a long cycle of start, then ticks against live MCP, then stop with the mind saved;
- **its own** tick interval and **its own** sleep interval for each employee;
- polling of those READ tools that the expert marked with the `poll` checkbox (the laboratory
  knows only the four mock tools of `1c_erp`);
- an approval queue in the same window where Start was pressed.

The role `procurement` already contains a live HTTP server `drivemcp`
(`http://localhost/DriveDemo/hs/mcp`) and a set of tools for stock, suppliers,
budget, and orders — Discover reaches it. WRITE execution and sensor polling
from the configurator do **not** go to that server. The gap is exactly here: the organs
are written down, and there is no body-host.

```
Role (YAML)          Employee (this document)         World
────────────         ─────────────────────────        ───
mcp_servers    →     composite organ registry    →    MCPTransport.call_tool
mcp_capabilities     BusinessAgentRuntime.tick        (mock | http | sse)
seed / affect        hippocampus + A(t) + checkpoint
                     ApprovalGate                     a human in the GUI
```

---

## 1. Separation of entities (do not mix them)

| Entity | What it is | Where it lives | Can it be “started” |
|---|---|---|---|
| **Role** | A description of the work: servers, organs, risk, seed, affect | `nowa_roles/<role_id>/config.yaml` | No. A role is a catalogue |
| **Employee** | A named NOWA instance plus a list of `role_id` plus a rhythm (tick/sleep) plus a life cycle | `nowa_employees/<agent_id>/employee.yaml` plus a mind checkpoint | Yes: start / stop |
| **Session** | A live runtime: mind, transports, approval queue, and a tick thread | in the host memory while the GUI process is alive; the mind is written to disk on Stop | This is what “started” means |

The invariants of the virtual-employee architecture remain in force:

1. An employee is a sovereign unit. The tool registry is **per-employee**. Two
   employees with one role are two hippocampi, two vectors A(t), and two approval queues.
2. Learning occurs only during sleep (`sleep_cycle`). Sleep does **not** follow from the fact of a tick;
   its period is set separately and is counted in **wall-clock seconds**, not in
   a number of ticks (section 5.6).
   Since #13: waking outcomes go to the labile tier, stable values change only in `Agent.sleep()`; the employee host passes `dt` ([issue-13-demo-virtual-company.en.md](../../../Docs/specs/issue-13-demo-virtual-company.en.md)).
3. The mind does not import MCP. Basal-ganglia channels are WRITE `tool_id` values plus `wait_and_monitor`.
4. HIGH_WRITE and IRREVERSIBLE are not bypassed by A(t) and are not bypassed by the Start button.
5. MotorAdapter is **not** an extension point. WRITE parameters are assembled by
   `SchemaBinder`.

**Consequence for the UI:** the employee list is an adjacent section of the main screen
of the configurator, not an eighth tab of the role editor. The role editor cannot
Start. The employee card cannot edit the role `config.yaml`.

---

## 2. Information architecture of the GUI

The configurator is launched by the same `run_role_configurator.bat`. The main screen
becomes two sections (roles on the left, as now; employees on the right).

```
┌─────────────────────────────────────────────────────────────────┐
│  NOWA Role Configurator                          [EN] [RU]      │
├──────────────────────────────┬──────────────────────────────────┤
│  Company roles               │  Employees                        │
│                              │                                   │
│  Procurement manager      ✓  │  Buyer A           ● stopped     │
│     procurement · 8 tools    │     roles: procurement            │
│                              │     tick 1s · sleep ≥ 1h          │
│  [+ New role]  [Open]        │     [Start]  [Open]               │
│                              │                                   │
│                              │  Operator          ● running     │
│                              │     roles: procurement, sales     │
│                              │     tick 60s · pending: 1         │
│                              │     [Stop] [Open]                 │
│                              │                                   │
│                              │  [+ New employee]                 │
└──────────────────────────────┴──────────────────────────────────┘
```

Employee statuses (exactly these strings; no free text in the badge):

| Code | UI | Meaning |
|---|---|---|
| `stopped` | stopped | no session; the mind is on disk if it has already worked |
| `starting` | starting | connecting to MCP, restoring or seeding memory |
| `running` | running | the tick thread is going |
| `sleeping` | sleeping | `sleep_cycle` is in progress (the session is alive; this is not Stop) |
| `awaiting_approval` | awaiting approval | there is a PENDING item; ticks **continue**, and the WRITE of this action_id does not leave |
| `stopping` | stopping | finish the tick, write the checkpoint, close the transports |
| `error` | error | the session has been taken down; the checkpoint is written if the mind was assembled in time; the text is on the card |
| `stale_roles` | (a plaque, not a badge) | the session is `running`, and role YAML changed after Start — a restart is required |

A double click, or “Open”, on an employee opens the **employee card** (not the role editor).

There is **no** limit on the number of employees or on the number of simultaneous `running` sessions.
Each `running` session has its own thread, its own registry, and its own approval queue.

### 2.1 “New employee” dialog

```
┌─────────────────────────────────────────────┐
│  New employee                                 │
│                                               │
│  Name: [Buyer A                           ]   │
│  id:   [buyer_a]  (slug, unique)              │
│                                               │
│  Roles (at least one, only valid ones):       │
│  [x] procurement — Procurement manager        │
│  [ ] sales — …                                │
│                                               │
│  Rhythm                                       │
│  Tick:    [1] seconds    (example: 1 or 60)   │
│  Sleep no more often than once per: [3600] s  │
│                                               │
│         [Cancel]            [Create]          │
└─────────────────────────────────────────────┘
```

- `agent_id`: `[a-z][a-z0-9_]{1,47}`, unique in `nowa_employees/`.
- An invalid role (`RoleConfigError`) is **disabled** in the checkbox.
  Warnings do not block.
- After creation the file is written immediately. There is no mind checkpoint yet — the first
  Start creates a new mind and, if memory is empty, sows the seed.

### 2.2 Employee card

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Employees     Buyer A                     [● running]        │
├─────────────────────────────────────────────────────────────────┤
│  Roles:  [procurement ×] [+ add a role]                          │
│          (role membership — only while stopped)                  │
│                                                                 │
│  Rhythm: tick [  1 ] s    sensor poll [ 30 ] s                   │
│          sleep no more often than [ 3600 ] s                    │
│          sleep window (hours) [ 2 ]–[ 5 ]   fatigue [ 0.85 ]    │
│          (tick and sleep can be changed live; role membership cannot) │
│                                                                 │
│  MCP: drivemcp  http  ok · 1c_erp  mock  ok                     │
│  Organs: 6 READ / 1 WRITE · last sensor 12s ago                 │
│  Memory: checkpoint 14:02 · 128 episodes                         │
│                                                                 │
│  Roles changed after start — restart the employee               │
│  in order to pick up the new YAML.                 [Restart]    │
│                                                                 │
│  [Start]  [Stop]     Stop is always available, including error  │
│                                                                 │
│  Approval queue                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ mcp__drivemcp__create_purchase_order                      │  │
│  │ supplier_id=…  sku=…  qty=45                              │  │
│  │ [Approve] [Reject] [Edit params]                          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Tick log (tail)              Memory (narrative, as in dry-run) │
│  t=14 action=mcp__drivemcp__… When stock is low → …             │
│  t=15 wait_and_monitor                                          │
└─────────────────────────────────────────────────────────────────┘
```

UX rules:

- **Start** is unavailable while there is no role, while the status is not `stopped` or `error`,
  and while the composite configuration does not pass `validate_role_config` (section 4).
- **Stop** is a cooperative kill switch: a flag, finish the current tick, a **full
  checkpoint of the mind** (section 5.7), close the transports, status `stopped`.
  Not `kill -9`.
- **The set of `role_ids`** changes only while `stopped`. This is the employee card,
  not the role editor.
- **The role editor** remains available while an employee is `running`. The session
  holds the composition loaded at Start. After a role YAML is saved, the cards of
  the affected `running` employees show the `stale_roles` plaque and a
  **Restart** button (Stop with a checkpoint, then Start with the new composition and the **restored**
  mind). The user decides when to restart; the host does not restart by itself.
- Closing the configurator window while employees are live opens a dialog: “stop N
  employees and save memory?” (Yes by default). Each follows the same
  Stop path as the button.

The dry run on the role tab is **left untouched**. It is a check of the configuration, not an employee.

### 2.3 Approval — the card only (Q-H-4)

A human approves a WRITE **only** on the employee card: the queue, and the buttons
Approve, Reject, and Edit params. In the employee list a counter
`pending: N` is admissible — it is an invitation to open the card, not a separate decision channel.

Forbidden in v1: a toast, a sound, a modal window on a tick. The configurator does not
steal focus if the role editor is open. A missed approval
stays in the queue until the human enters the card (or stops the
employee: PENDING items go into the sidecar).

### 2.4 Role “Tools” tab — the poll checkbox (Q-H-9)

On the card of each tool, beside “included in the role” and “approval required”,
a checkbox **“Poll as a sensor”** (`poll`) appears. This is a field of the role, not
of the employee: which organs the host calls itself is decided by the role expert.

| Tool | Checkbox |
|---|---|
| READ_ONLY, included in the role | available; the user sets it explicitly |
| WRITE (any risk) | off and **disabled** — polling a muscle is forbidden |
| Not included in the role | disabled; `poll` is not written into YAML until the tool is included |

The default when a tool is included in a role, and on Discover, is **`poll: false`**.
The host never starts hitting a base “because the schema is empty” — only
the checkbox does. The existing role `procurement`, within this delivery, receives
explicit `poll: true` on those READ tools that must be sensors (stock,
suppliers, budget, reorder point, demands) — a YAML migration, not a runtime
heuristic.

If `poll: true` and `input_schema` has `required` fields that nothing can
fill: the host does **not** call the tool on that tick, writes a warning to the log,
and the session does not fall. The same tool card then shows
`poll_defaults` fields (one for each required field). While the defaults are empty and
WorldState has not closed the required fields, the sensor stays silent.

Fragment of role YAML:

```yaml
- tool_id: mcp__drivemcp__get_stock_levels
  risk_level: read_only
  poll: true
  poll_defaults: {}          # not needed: there is no required

- tool_id: mcp__drivemcp__list_metadata_objects
  risk_level: read_only
  poll: true
  poll_defaults:
    metaType: Catalogs       # otherwise the host will not call the tool itself
```

---

## 3. Data: `employee.yaml` and the checkpoint

A new root beside the roles, not inside `nowa_roles/`:

```
Demo/Virtual company/src/nowa_employees/
  <agent_id>/
    employee.yaml
    .history/employee_<timestamp>.yaml
    mind.pkl                 # full mind checkpoint (section 5.7)
    session_sidecar.json     # WorldState, approval queue, sleep scheduler
```

Schema of `employee.yaml` v1:

```yaml
schema_version: 1
agent_id: buyer_a
display_name: "Buyer A"

# Order is the order of classifier overlay and of alias merge (section 4).
# At least one id.
role_ids:
  - procurement

# The rhythm of this employee, not a property of the role.
# Tick = how often the mind takes a decision (wall-clock seconds).
# One employee may have 1, another 60 — both are valid.
tick_interval_s: 1.0
sensor_refresh_interval_s: 30.0

# Sleep is counted in wall-clock seconds, not in a number of ticks.
# min_interval_s is anti-thrash: sleep no more often than once per this interval.
sleep:
  min_interval_s: 3600          # 1 hour; at a tick of 1 s this is not “every tick”
  circadian_window: [2, 5]      # hours of the local day; [0, 0] = off
  fatigue_threshold: 0.85       # Process S; null = do not wake by fatigue

seed_intuition: true            # only if memory is empty (section 5.1)
auto_execute: false             # never lifts HIGH_WRITE / IRREVERSIBLE

created_at: "2026-08-27T12:00:00"
updated_at: "2026-08-27T12:00:00"
```

There is **no** `mcp_overrides` (a private base for the same role) in v1. The account and the URL live
in the role YAML. Different bases for one role are a stage after v1; the schema is ready
to gain a list, and the host does not yet read such a field.

Rhythm validation on load:

| Field | Rule |
|---|---|
| `tick_interval_s` | `> 0`, a reasonable ceiling of 86400 (one day). Otherwise `EmployeeConfigError` |
| `sensor_refresh_interval_s` | `>= tick_interval_s` is recommended, not required; `> 0` |
| `sleep.min_interval_s` | `>= 0`; `0` is allowed only as an explicit “laboratory” mode and requires confirmation in the UI (“sleep will be able to occur on every tick”) |
| `circadian_window` | two integers 0–23; `[0, 0]` or `start == end` means the window is off (as as-built) |

File constraints:

| # | Rule |
|---|---|
| **E1** | The GUI does not write `nowa_roles/**` when an employee is created or started |
| **E2** | `role_ids` refer to existing `nowa_roles/<id>/config.yaml` files |
| **E3** | An empty `role_ids` is a load error, not “an employee with no organs” |
| **E4** | The checkpoint (`mind.pkl`) belongs to this `agent_id`; a foreign file is not mixed in |

---

## 4. Merging roles into a composite `RoleConfig`

Assigning several roles is a **union of organs**, not “two brains” and not
a runtime switch of persona. One `BusinessAgentRuntime`, one registry,
one `WorldState`.

An organ is **already** identified as `tool_id = mcp__<server_id>__<tool_name>`.
The same human tool on different MCP servers is two different organs
(`mcp__1c_erp__get_stock_levels` is not `mcp__drivemcp__get_stock_levels`).
A collision “two get_stock_levels” does **not** arise when roles are merged, as long as
the tools are bound to different `server_id` values. This closes Q-H-1.

A true duplicate is two roles that enabled **the same** `(server_id, tool_name)`.
That is one organ, not a name conflict: the records merge into one instance.

A new module (the logic is not in the GUI): `nowa_body/role_compose.py`.

```text
compose_roles(role_ids, roles_root) -> RoleConfig
```

Each id is loaded through `load_role_config` (G1 remains). Then the merge.

| Field | Rule |
|---|---|
| `role_id` | composite: `"+"`.join(role_ids) — a label, not a path on disk |
| `display_name` | `" + ".join(the display_name of each role)` |
| `mcp_capabilities` | the key is `tool_id` (server plus tool name). The first time, take it. A repeat of the same `tool_id`: if the capability is **equivalent** (risk, schema, approval, tags, **`poll`**, `poll_defaults`) — one instance; if the fields diverge — `RoleConfigError` naming both roles and the `tool_id` |
| `mcp_servers` | the key is `server_id`. A repeat: the same transport, url, and username — one server. A divergence of url, transport, or username is an error (this is no longer “the same MCP”). Password: a non-empty value wins over an empty one; both non-empty and different is an error |
| `affective_mapping` | union by event name. The same name with different valence, arousal, or tags is an error |
| `seed_corpus` | concatenation in the order of `role_ids`, then `validate_role_config` |
| `param_bindings` / `field_aliases` | merge of keys; a repeated key takes the value of the **later** role, plus `warnings.warn` |
| `event_classifier` | every given callable as an overlay, in the order of `role_ids`. None at all is acceptable |
| `motor_adapter` | **ignored** |

After the merge, the same `validate_role_config`. An invalid composition means Start
is forbidden.

The fields `poll` and `poll_defaults` are parsed in `role_config._parse_capability` and
live on `MCPCapability` (new fields, default `poll=False`,
`poll_defaults={}`). The GUI does not construct a capability by bypassing the loader (G1).
`poll: true` on a WRITE at load time yields `RoleConfigError` (the UI cannot be bypassed).

---

## 5. Host: `EmployeeSession` (not `BodyLabSession`)

The laboratory remains for the dry run and for Body Lab. A live employee is a new class.

Proposed modules:

```
nowa_body/
  employee_config.py          # load/save employee.yaml
  role_compose.py             # compose_roles()
  mcp_router.py               # server_id → MCPTransport
  sensor_poller.py            # which READ tools to call, and with which arguments
  employee_checkpoint.py      # mind.pkl and the sidecar through AgentStorage
  employee_session.py         # runtime and the cooperative loop
  gui_configurator.py         # the employee section (view)
  gui_employee_controller.py
```

`nowa_sandbox` is not imported.

As-built, `SleepScheduler` counts anti-thrash in **ticks**
(`min_ticks_between_sleep`). For employees with different `tick_interval_s` this
breaks the meaning (“3600 ticks” at a tick of 1 s is one hour, and at a tick of 60 s is 60 hours).
The host is obliged to feed the scheduler **wall-clock time**: either extend
`SleepScheduler` with a field `min_interval_s` and compare elapsed seconds, or
use a wrapper that converts `min_interval_s / tick_interval_s` only as a
fallback. The canon of the specification is **wall-clock seconds** (section 5.6). The laboratory
and its tests are not obliged to change in this delivery.

### 5.1 Assembly of the session at Start

1. Read `employee.yaml`.
2. `compose_roles(role_ids)` — a snapshot at the moment of Start. Later edits
   of role YAML do not change this session until the user presses Restart.
3. Build `MCPToolRegistry(agent_id)` (`build_tool_registry`).
4. For each **enabled** server, open a transport:
   - `mock` yields `MockMCPClient` with the role catalogue (as Discover does), not the four
     hard-wired laboratory tools;
   - `http` or `sse` yields `mcp_transport_from_server`;
   - `stdio` is refused with a clear error.
5. Ping: `list_tools()` on each live transport. An unavailable HTTP server yields
   `error`, Start fails, and there is **no** silent fallback to mock.
6. Create the skeleton of a mind: `AgentFactory.spawn_default(agent_id=...)` if
   the core is available, otherwise the fallback used by `create_lab_agent`. No `force_action`.
7. Memory:
   - if a checkpoint exists and memory is **not empty**, `load_agent` into this skeleton,
     and do **not** call seed;
   - if there is no checkpoint **or** memory is empty (no hippocampal episodes),
     and `seed_intuition: true`, call `build_seeder(composed).seed_agent`;
   - a broken pickle yields status `error`, and seed is **not** substituted silently
     (that would destroy identity). On the card, the action “reset memory”
     is explicit and requires confirmation.
8. `BusinessAgentRuntime`: ApprovalGate, encoder, `param_bindings` and
   `field_aliases`, SleepScheduler from the employee YAML,
   `sensor_refresh_interval_s`, and **`simulated_tick_seconds = tick_interval_s`**
   (Process S grows from the time lived at this rhythm, not from “1 tick = 1 s”
   for everyone).
9. `auto_execute=true` lifts approval only for WRITE below HIGH_WRITE.
   HIGH_WRITE or IRREVERSIBLE yields `HardConstraintViolation`, and Start is cancelled.
10. Restore the sidecar if there was one: `WorldState`, the PENDING queue
    (WRITE items not yet executed), and the SleepScheduler counters.
11. Start the worker (section 5.4).

“Memory is empty” means there is no `mind.pkl`, or after load the hippocampus has 0 experiences.
A later Start after Stop always follows the restoration branch, not the seed branch.

### 5.2 Call routing (`mcp_router`)

`tool_id` is `mcp__<server>__<name>` (`split_tool_id`). READ and WRITE go to
the transport of that `server_id`. The host does not branch on “Drive” or “1C”.

The WRITE executor is **only** `ApprovalGate.mcp_executor` (B5).

### 5.3 Sensor polling

The host does **not** poll “every READ”. A sensor is a capability with `poll: true`
(and only READ_ONLY — the loader already guarantees that). The three hard-wired laboratory
tools are not used.

Order of call arguments when `poll: true`:

| Condition | Behaviour |
|---|---|
| `poll_defaults` are set | call with them (SchemaBinder may supplement them without overwriting the defaults) |
| `required` is empty | call with `{}` |
| `required` is non-empty, and `SchemaBinder` fills every required field from `WorldState` | call with those params |
| otherwise | skip this cycle, and write a warning to the employee log |

The poll interval is the employee’s `sensor_refresh_interval_s`, not the tick rate.
The contract of `BusinessAgentRuntime.tick` is already of that form.

Observations:

```python
{
  "agent_id": employee.agent_id,
  "tool_results": { tool_id: envelope, ... },
}
```

There are no domain keys `stock`, `suppliers`, or `budget`. An error of one READ yields
an envelope `{status: "error", ...}`, and the other sensors of the cycle are still polled.
A dead transport at start is step 5 of section 5.1.

### 5.4 Life cycle of the thread

v1: **one daemon thread per employee** inside the Tk process. There is no limit N.
The reason it is not a subprocess: the approval queue and the log are in the same window, with no RPC.

```
while not stop_flag:
    result = runtime.tick(sensor_fetcher, now=datetime.now())
    enqueue UI snapshot (plain dicts)
    sleep(current_tick_interval_s)   # read from employee.yaml / the card
```

Tk is not called from the worker. The card reads the queue through `after(200 ms)`.

A change of `tick_interval_s` or `sleep.min_interval_s` on the card is **live**:
the next `sleep()` of the loop and the next `should_sleep` take the new values.
A live change of `role_ids` is forbidden (stopped only). A change of role YAML
is a plaque, and a Restart is required.

Stop:

1. The UI sets `stop_flag`.
2. The worker exits after the current `tick` or `call_tool` (v1 waits for the transport timeout,
   30 s by default).
3. A full checkpoint (section 5.7). If the write failed, the status is `error`,
   the session is still taken down, and the card shows the save-error text.
4. Close HTTP sessions if the client can.
5. Status `stopped`.

Two employees may call one MCP URL: the transport may be shared; the registry
and the checkpoint may not.

### 5.5 Approval while running

- A PENDING WRITE: status `awaiting_approval` if the queue is non-empty; ticks continue.
- The decision is **only** the employee card (`complete_approval` from the UI thread).
  The list shows `pending: N`. There is no toast, no sound, and no modal.
- Editing params is `modified_params`, as in `ApprovalGate.decide`.
- On Stop, the PENDING queue goes into the sidecar and returns on the next Start
  (a WRITE that has not yet entered the world is not lost).

### 5.6 Sleep: not every tick, and the period is its own

Sleep is consolidation (`sleep_cycle`), not “skipping a tick”. Calling it on
every `tick` is forbidden: that is the thrashing of which the
as-built `min_ticks_between_sleep` warns.

The laboratory problem that this specification repairs for employees:

- the scheduler historically counts the pause in **ticks**;
- employees have different ticks (1 s versus 60 s), so “3600 ticks” is a different
  amount of human time;
- Process S (`update_waking`) already accepts `elapsed_seconds`.

Host rules:

1. `simulated_tick_seconds = tick_interval_s`. One wall-clock hour of waking
   gives the same growth of Process S to a 1-second employee and to a 60-second
   employee.
2. Anti-thrash is `sleep.min_interval_s` in **wall-clock seconds** since the
   last `mark_slept`. Until that time has passed, `should_sleep` is false, even
   if the circadian window is open and fatigue is high.
3. If the pause has elapsed: sleep when (the circadian window is open) **or** (Process S
   is at least `fatigue_threshold`, if a threshold is set). The window `[0,0]` or `start==end`
   switches the circadian branch off. `fatigue_threshold: null` switches the fatigue branch off.
   If both branches are off, the employee does not sleep by itself (only a future explicit
   “put to sleep” button, which is not in v1).
4. While `sleep_cycle` runs, the badge is `sleeping`; this is not Stop. The worker
   does not start the next tick until sleep returns.
5. The default for a new employee: `min_interval_s: 3600`, window `[2, 5]`, threshold
   `0.85` — the laboratory canon, but in seconds, not in ticks.
6. The UI must show that sleep and the tick are different controls. Hint: “The tick is how
   often the employee looks at the world. Sleep is how often experience is consolidated.
   Sleep on every tick will break learning.”

### 5.7 Mind checkpoint (Stop, then disk, then Start)

An employee must not be forgotten. Stop fixes the state **at the moment of the stop**;
the next Start raises the same employee.

Contents of the checkpoint:

| File | Contents |
|---|---|
| `mind.pkl` | Everything that `AgentStorage.save_agent` writes when `agent=` is passed: hippocampus, cortex, selector (plus channel metadata), A(t), affect, sleep_manager, neuromodulators, value layer, conflict arbitration, wakefulness / Process S, and the other fields that storage already serialises |
| `session_sidecar.json` | `WorldState` (results/entities/scalars/stats), PENDING approval records, elapsed `sleep.min_interval`, tick_index, the timestamp of the stop, and the hash or mtime of the roles with which the session was assembled (for the stale plaque) |

Order on Stop: first `mind.pkl` (atomically: write `mind.pkl.tmp`, then
replace), then the sidecar. Reading on Start: the mind, then the sidecar; a broken sidecar
does not cancel the restored mind (the approval queue is then empty, and WorldState
fills from the first READ calls).

A restart because roles changed: Stop (checkpoint), then compose the new YAML, then Start with
the same `mind.pkl`. Organs in the selector are registered again after compose
(`register_organs_on_agent`); old channels that are no longer in the composition
remain in the selector metadata, but the runtime does not offer them as muscles.

An explicit “reset memory” on the card (while stopped) deletes `mind.pkl` and the sidecar
after confirmation. The next Start means empty memory, and therefore a seed if seeding is enabled.

---

## 6. Relation to the end goal (bases through MCP on the NOWA platform)

The platform body already can: Discover over HTTP, `tool_id` as a channel,
`SchemaBinder`, ApprovalGate, and an envelope `status`. The host of this specification is
a long-running call of the same contract, plus the rhythm and the memory of an employee.

A new base is a new `mcp_servers[]` entry in a role, plus the tools that are enabled, plus `poll` on
the READ tools that are needed, plus a seed, and then assignment of the role to an employee and Start. The host does **not**
contain the strings `Drive`, `1c`, or `PurchaseOrder`.

Acceptance order (Q-H-6): **mock first, then Drive**. A live Drive does not
block the merge of the host and is not part of pytest CI. The “metadata clerk” role
is a separate task after the host.

### 6.1 Mock stage (part of DoD v1)

Automated tests and a manual run in the configurator against `transport: mock`:
create an employee, start, ticks, the approval queue (the card), stop,
a checkpoint, and a second start without a seed. CI: `pytest -q -m "not slow"`.

### 6.2 Drive stage (after a green mock, a manual checklist)

When the mock host works, the same employee and the role `procurement`, with `drivemcp` http
already written down:

1. READ sensors have `poll: true` (a YAML migration).
2. Start against the live `hs/mcp` (the publication is available locally).
3. The log shows real READ calls, not the four mock warehouses of the laboratory.
4. Stop, then a checkpoint, then Start without a repeated seed.
5. The WRITE `create_purchase_order` waits on the **card** until a human approves it.

Item 6.2 does not have to be green in order to close the host code. It does have to be
passed before one declares that “the employee works with a base”.

---

## 7. Constraints (obligatory)

| # | Constraint |
|---|---|
| **H1** | The GUI does not construct `MCPCapability` or `SeedEpisode` by bypassing `role_config` or `compose_roles` |
| **H2** | The only WRITE point is `ApprovalGate` |
| **H3** | HIGH_WRITE and IRREVERSIBLE cannot be made auto_execute |
| **H4** | `decision_only=True` on a waking tick; the episode is stored after a known outcome |
| **H5** | Start with an invalid role or an invalid composition is impossible |
| **H6** | An unavailable live transport at start yields `error`, not a mock fallback |
| **H7** | `role_ids` change only while `stopped`. Role YAML may be edited at any time; a running session holds the Start snapshot |
| **H8** | The worker does not touch Tk; the UI is not blocked on `call_tool` |
| **H9** | The host does not import `nowa_sandbox` and does not add axes to `AffectiveSpace` |
| **H10** | A role dry run does not start an `EmployeeSession` |
| **H11** | Sleep is no more frequent than `sleep.min_interval_s` of wall-clock time; the tick and sleep are independent fields |
| **H12** | Seed only when memory is empty. Start after Stop does not re-seed the hippocampus |
| **H13** | A stop without a successful write of `mind.pkl` is not counted as a “normal stopped” without a message about the save error |
| **H14** | There is no limit on the number of employees or on the number of simultaneous `running` sessions |
| **H15** | Approval: the card only, plus a `pending` counter in the list. No toast, no sound, no modal |
| **H16** | The host polls only `poll: true`. The checkbox is on every tool of the role; a WRITE cannot be poll |
| **H17** | CI and DoD v1 are the mock. A live Drive is the next manual step, not pytest |

---

## 8. Tests (minimum)

File: `Demo/Virtual company/tests/test_employee_host.py` (plus the controller).

- `compose_roles` of one id is equivalent to `load_role_config` of that role.
- Two roles, one tool **name**, different `server_id` values: two organs, not an error.
- Two roles, the same `tool_id`, equivalent capabilities: one organ.
- The same `tool_id` at a different `risk_level`: `RoleConfigError`.
- Two servers with one `server_id` and different `url` values: an error.
- `sensor_poller`: the poll set contains only `poll: true`; a WRITE with `poll: true` does not
  load; a READ with `poll: false` is not called, even if required is empty.
- GUI Tools: the poll checkbox is on READ; on WRITE it is disabled.
- A mock session: start, then N ticks, then stop, then `mind.pkl` exists, then start, then
  the episode count is at least that after the first stop, and a second seed does not add duplicates
  (or the seeder was not called — an explicit check).
- An empty employee (no mind): start with `seed_intuition: true` seeds the corpus.
- `tick_interval_s=60` does not turn `sleep.min_interval_s=3600` into “sleep
  every 60 ticks”; over a window shorter than an hour, under stable pressure, sleep occurs 0 times.
- `auto_execute=True` does not pass for HIGH_WRITE.
- Routing: `mcp__alpha__x` does not call the transport `beta`.
- i18n EN/RU, `assert_string_parity`. The UI word is “employee”, not “agent”.

Do not run a live Drive in CI. The checklist of §6.2 comes after the mock, not instead of it.

---

## 9. Definition of Done (delivery v1)

- [ ] Main screen: the employee list beside the role list
- [ ] CRUD of `employee.yaml`: create, open, assign and remove roles (while stopped),
      set the tick and sleep, backup into `.history/`
- [ ] `compose_roles` keyed by `(server, tool)` / `tool_id`, with collision tests
- [ ] Start and Stop on the mock, with a tick log
- [ ] The fields `poll` and `poll_defaults` in role YAML, on `MCPCapability`, and on the Tools tab
- [ ] Migration of `procurement`: explicit `poll: true` on READ sensors
- [ ] The host polls only `poll: true` (not every READ, and not the four laboratory tools)
- [ ] HTTP transport from the composite `mcp_servers` (the code exists; a live Drive is §6.2)
- [ ] The approval queue only on the card, plus `pending: N` in the list; no toast, sound, or modal
- [ ] A checkpoint on Stop, restoration on Start, and a seed only if memory is empty
- [ ] Sleep in wall-clock seconds, independent of the tick; both fields on the card
- [ ] Editing role YAML while running, plus a stale plaque, plus Restart at the user’s choice
- [ ] Stop on window close, with memory written
- [ ] RU/EN; the role dry run is not broken
- [ ] The tests of §8; regression of the Demo with `pytest -q -m "not slow"`

Outside DoD v1: a live Drive run (§6.2 is the next step after the mock),
`mcp_overrides`, a subprocess, stdio MCP, a host without Tk, and the “metadata clerk” role.

---

## 10. Stages

| Stage | Contents |
|---|---|
| **A1 — DoD v1** | Employee, compose, rhythm, start/stop, checkpoint, **mock**, the poll checkbox, approval on the card |
| **A2** | A manual run of the same host against a live Drive (§6.2) |
| **B** | `mcp_overrides`; subprocess isolation |
| **C** | A host without Tk (a service or a CLI) |

The mind checkpoint is in A1. The HTTP client code already exists; A2 checks it live.

---

## 11. Decisions taken (every Q-H is closed)

1. Several roles are a union of organs. The organ key is `tool_id` (MCP plus the tool name).
2. Concurrent employees: no limit, N threads in the GUI process.
3. The v1 process is a thread, not a subprocess.
4. Memory: a full checkpoint on Stop, a full restoration on Start.
5. The name in the UI is “Employees”; the file is `employee.yaml`.
6. Acceptance: mock first (DoD / CI), then a manual Drive (§6.2). The metadata-clerk role
   comes after the host. (Q-H-6)
7. The tick is configured **per employee** (`tick_interval_s`: 1 s, 60 s, and so on).
8. Sleep is configured **per employee** in wall-clock seconds, not “every tick”.
9. `auto_execute` is false by default.
10. A warning on a role does not block assignment; an error does.
11. A mixed mock and http composition is normal.
12. Seed only if memory is empty.
13. There is no `mcp_overrides` in v1; different bases for a role are stage B.
14. The role editor is not blocked by a running employee; a manual restart is required
    in order to pick up the YAML.
15. Approval: the card only, plus `pending: N` in the list. No toast, no sound,
    no modal. (Q-H-4)
16. Sensor polling: an explicit `poll` checkbox on every tool of the role. The default is false.
    WRITE poll is forbidden. `poll_defaults` apply when a sensor has required fields. (Q-H-9)

---

## 12. Question log (closed)

| ID | Decision |
|---|---|
| Q-H-1 | The merge key is `tool_id` (server plus name). Different MCP servers are different organs |
| Q-H-2 | No limit on the number of `running` sessions |
| Q-H-3 | A full checkpoint on Stop, restoration on Start |
| Q-H-4 | The card only (plus a counter in the list) |
| Q-H-5 | `mcp_overrides` is not in v1 |
| Q-H-6 | Mock first, then Drive; the metadata clerk later |
| Q-H-7 | Seed only if memory is empty |
| Q-H-8 | UI: “Employee” |
| Q-H-9 | A `poll` checkbox on every tool |
| Q-H-10 | A role may be edited; the session holds the Start snapshot; restart is manual |

---

*Employee host v1.0. There are no open questions — the document can be handed
to implementation (stage A1: mock). The role GUI gains a poll checkbox; beside it
appears the employee entity, with a rhythm, a memory, and a runtime.*
