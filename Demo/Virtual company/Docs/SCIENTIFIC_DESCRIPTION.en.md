# Virtual Organisation: Scientific Account of the Platform

Russian version: [SCIENTIFIC_DESCRIPTION.ru.md](SCIENTIFIC_DESCRIPTION.ru.md)

### 1. Subject

The platform studies the embodiment of a NOWA agent in the role of an employee. It contains two contours that do not import one another.

The procurement sandbox (`src/nowa_sandbox/`) is a controlled market. The agent selects a supply strategy before contact with an external information system. The protocol body and the employee host (`src/nowa_body/`, role `src/nowa_roles/procurement/`) map tools of an external server onto organs. The core of that mapping resides in the repository `src/mcp_body/`.

Scientific description of the complex: [SCIENTIFIC_DESCRIPTION.en.md](../../../Docs/SCIENTIFIC_DESCRIPTION.en.md). Normative specifications in this directory retain their contracts; the bilingual preface of each refers here.

### 2. Shared invariants

The agent is a sovereign unit: its own memory, its own affective space, and the absence of a central dispatcher. Consolidation of slow memory is performed in `sleep_cycle`. During waking, weights of slow memory are not updated systemically. The canonical vector \(A(t)\) is not extended by axes of budget or urgency. Monetary and organisational bounds lie in the body. A write into the external world passes through the gating loop. A language model does not assemble organ parameters.

### 3. Procurement sandbox

The world sets demand, deliveries, holding costs, supplier defaults, and bankruptcy. The encoder passes categorical context tokens to the agent; the world object is not passed. The call `agent.step` runs in decision mode. Concrete product, supplier, and quantity are resolved by `ProcurementMotorAdapter` — the body of the strategy in this sandbox, distinct from the universal schema binder of the protocol body. After the outcome is known, the episode is stored. World physics advances by `world.tick`. Learning occurs in the call `sleep_cycle` with period `sleep_every_n_days`.

Since issue #96 the day and quarter loops live in `scenario_trainer.py` against the `Scenario` protocol; the buyer plugin is `ProcurementScenario`, and `SandboxTrainer` keeps the previous public API. Generic modules must stay free of procurement vocabulary. Developer guide: [issue-96-sandbox-scenario.en.md](../../../Docs/specs/issue-96-sandbox-scenario.en.md).

A quarter builds a new world from the seed `base_seed + quarter - 1`. The agent's state is what carries across quarters.

The curriculum has two stages. Stage 1a rotates suppliers every quarter and gates graduation on criteria that do not depend on supplier identity. Stage 1b keeps the supplier roster and gates graduation on the criteria that do depend on it, with a guard against regression relative to the typical level of Stage 1a. Graduation from Stage 1b requires a run of consecutive quarters that pass the threshold and the guard. The Stage 1a baseline is the median of quarters, with a floor that takes the interquartile range into account. World configuration bounds structurally infeasible quarters (lead time, demand, stock).

The six fitness criteria are cost efficiency, stockout avoidance, budget discipline, supplier diversification, decision consistency, and reaction to risk events. The evaluator does not drive the basal ganglia.

### 4. Recorded laboratory observations

The observations below are those preserved in platform artifacts. The present documentation revision did not recompute them.

Run v1.0, 30 quarters, `configs/default_world.yaml`, seed 42, artifacts `results/sandbox_run_001.json` and the corresponding checkpoint. Graduation on all six criteria is marked in quarters 17 and 19; the run continued to quarter 30 with stop-on-graduation disabled. Recomputation of the same quarters under the four-criterion Stage 1a rule yields 7 of 30 rather than 2 of 30. Means of the first five and the last five quarters:

| Criterion | Threshold | First 5 | Last 5 |
|---|---:|---:|---:|
| cost_efficiency | 0.60 | 0.599 | 0.481 |
| stockout_avoidance | 0.85 | 0.696 | 0.813 |
| budget_discipline | 0.95 | 1.000 | 1.000 |
| supplier_diversification | 0.40 | 0.394 | 0.133 |
| decision_consistency | 0.60 | 0.783 | 1.000 |
| reaction_to_risk_events | 0.50 | 0.777 | 0.856 |

The rise in decision consistency is accompanied by a fall in diversification: the agent settles on a supplier per product. Cost efficiency is the noisiest criterion.

Time budget of the same run: one `world.tick()` about 0.02 ms against a limit of 5 ms; the full run 9.3 min against a limit of 15 min; a quarter 7 s at the start and about 38 s by quarter 30 against a limit of 30 s. The growth is attributed to candidate search in hippocampal imagination in the core, up to saturation of episode capacity, rather than to `sleep_cycle`.

On seed 77, after the world bounds of v1.3, the interquartile range of stockout avoidance over 30 quarters fell from approximately 0.84 to 0.012; graduation is marked in 12 of 30 quarters (`results/RESULTS_v13.md`).

### 5. Divergences of the sandbox implementation from the early specification reference

The implementation preserves signatures and behavioural guarantees and diverges from the early reference where that reference contradicted its own checks. Material divergences: the critical-budget flag is tested before the high-utilisation flag; fitness counts orders accepted by the world, not the literal strategy label; quote noise is drawn from a generator bound to supplier, product, and day, so that a read does not change world state; a NaN quantity is rejected; motor-adapter priority includes inbound deliveries; the quarter seed equals `base_seed + quarter - 1`; waking feedback does not bypass the sleep-learning boundary; the graduation report separates criteria from metadata; Stage 1b uses the shared quarter loop with a supplier-carry flag; the checkpoint stores the supplier roster; an unknown stage is rejected; Stage 1b graduation requires a run of quarters; the Stage 1a baseline is the median, not the mean of the best; world initialisation ranges are bounded.

World physics and the training loop are bit-reproducible under a fixed seed. Cognitive state of the core depends on hippocampal decay against wall-clock time, so two runs of the same configuration diverge with execution duration. A late delivery changes supplier reputation and keeps the original arrival day. The agent selects a strategy; order parameters are resolved by the sandbox motor adapter.

### 6. Protocol body and employee host

A read tool is a sensor, a write tool is a muscle, and the tool identifier is a basal-ganglia channel. The channel `wait_and_monitor` permits refraining from action. Call parameters are assembled from the tool schema, the world state, and weights derived from \(A(t)\). The domain motor adapter of the sandbox is not the extension point of the protocol body.

A role is data (`config.yaml`) loaded by `role_config`. An employee is an instance of a mind (`employee.yaml`, `agent_id`) to which a role has been issued. Starting and stopping an employee does not edit the role description. Affective presets map role events onto impulses in the fixed axes of \(A(t)\).

High-risk writes and irreversible operations require external confirmation. The cognitive step of a tick runs in decision mode; the episode is committed after the outcome is known and contains one action event. The sleep scheduler is invoked separately from selection.

### 7. Reproduction

Dependencies: `pip install -r "Demo/Virtual company/requirements.txt"`.

Sandbox, from the platform directory:

```bash
python src/nowa_sandbox/run_sandbox.py --config configs/default_world.yaml --stage 1a --quarters 30
```

Sandbox laboratory: `python -m nowa_sandbox.gui_app`. Body laboratory: `python -m nowa_body.gui_app`. Role configurator: `python -m nowa_body.gui_configurator`.

Checks: `python -m pytest -m "not slow"` from the platform directory; the full suite includes tests marked for duration.

Outside the subject until both stages are confirmed separately: a mixed stage regime, carrying budget across Stage 1b quarters, and competition of several agents for the same suppliers.

## 8. Documents of the platform

Other documents of this platform:

- [Addendum: AffectiveSpace canon + body without MotorAdapter](NOWA_Body_Layer_AffectiveSpace_Body_Addendum.en.md)
- [NOWA Body Layer — As-Built Phase 1 and the MCP Integration Contract](NOWA_Body_Layer_Phase1_AsBuilt_MCP_API.en.md)
- [NOWA Body Layer — Patch v1.1](NOWA_Body_Layer_Phase1_Patch_v1.1.en.md)
- [NOWA Body Layer — Patch v1.2](NOWA_Body_Layer_Phase1_Patch_v1.2.en.md)
- [NOWA Body Layer — Phase 1 Specification](NOWA_Body_Layer_Phase1_Spec.en.md)
- [NOWA Body Layer — Role Configurator (RoleConfig)](NOWA_Body_Layer_RoleConfig_Spec.en.md)
- [NOWA Procurement Sandbox — Technical Specification](NOWA_Procurement_Sandbox_Spec.en.md)
- [NOWA Procurement Sandbox — Patch v1.1.1](NOWA_Procurement_Sandbox_Spec_v1.1.1_patch.en.md)
- [NOWA Procurement Sandbox — Patch v1.1](NOWA_Procurement_Sandbox_Spec_v1.1_patch.en.md)
- [NOWA Procurement Sandbox — Patch v1.2](NOWA_Procurement_Sandbox_Spec_v1.2_patch.en.md)
- [NOWA Procurement Sandbox — Patch v1.3](NOWA_Procurement_Sandbox_Spec_v1.3_patch.en.md)
- [NOWA Procurement Sandbox — Refactor v2.0](NOWA_Procurement_Sandbox_Spec_v2.0_refactor.en.md)
- [NOWA Role Configurator — the full canon of feelings and emotions](NOWA_Role_Configurator_Affective_Mapping_Spec.en.md)
- [NOWA Role Configurator — Employee Host (roles, then instance, then start/stop)](NOWA_Role_Configurator_Agent_Host_Spec.en.md)
- [NOWA Role Configurator — GUI Specification](NOWA_Role_Configurator_GUI_Spec.en.md)
- [NOWA Virtual Employees — Architecture Specification](NOWA_Virtual_Employees_Architecture_Spec.en.md)
- [NOWA Procurement Sandbox v1.1: two-stage curriculum](v1.1_two_stage_curriculum.en.md)
