# NOWA-Cognitive Project Documentation

Russian version: [00_INDEX.ru.md](00_INDEX.ru.md)

**Status (27 September 2026).** This index is superseded. Reading order: [INDEX.en.md](INDEX.en.md) and [SCIENTIFIC_DESCRIPTION.en.md](SCIENTIFIC_DESCRIPTION.en.md).

**Version:** 3.3  
**Last Updated:** 23 March 2026  
**Status:** Production Ready (Phase 5 EDPC + Phase 6 integrated + semantic similarity replacement)

---

## Documentation Structure

### Getting Started
- **[START_HERE.md](START_HERE.en.md)** - Start reading from here if you're new to the project
- **[QUICK_START_RU.md](QUICK_START_RU.en.md)** - Quick start guide (Russian)
- **[INSTALLATION.en.md](INSTALLATION.en.md)** - Installation and setup instructions

### Architecture and Design
- **[ARCHITECTURE.md](ARCHITECTURE.en.md)** - Overall system architecture
- **[Two-tier plasticity](../Docs/architecture/two-tier-plasticity.en.md)** - Labile vs stable learning (issue #13)
- **[SLEEP.md](SLEEP.en.md)** - Sleep consolidation order and parameters
- **[ARCHITECTURE_UPDATED.md](ARCHITECTURE_UPDATED.en.md)** - Current architecture map (EDPC + Phase 6)
- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.en.md)** - Project folder structure
- **[EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.en.md)** - High-level overview of the system
- **[Phase_4_Affective_Space_Spec.md](Phase_4_Affective_Space_Spec.en.md)** - Phase 4 (pre) affective space specification

### Core Components

#### Phase 1: Foundation
- Affective System (AffectiveState)
- Neuromodulator System (NeuromodulatorState)
- Basic action generation

#### Phase 2: Advanced Features
- **[README_AFFECTIVE_SYSTEM.md](README_AFFECTIVE_SYSTEM.en.md)** - Affective regulation
- **[Phase2_Wakefulness_PFC_Extension.md](Phase2_Wakefulness_PFC_Extension.en.md)** - Wakefulness and PFC
- **[spec_circadian_process_c.md](spec_circadian_process_c.en.md)** - Circadian Process C for wakefulness model
- **[NEUROMODULATORS_QUICK_REFERENCE.md](NEUROMODULATORS_QUICK_REFERENCE.en.md)** - Neuromodulator reference

#### Phase 3: Basal Ganglia (NEW - February 2026)
- **[Phase_3_Basal_Ganglia_Action_Gating_refactoring.md](Phase_3_Basal_Ganglia_Action_Gating_refactoring.en.md)** - BG specification
- **[REFACTORING_REPORT.md](../REFACTORING_REPORT.md)** - Complete refactoring report
- **[REFACTORING_SUMMARY.py](../REFACTORING_SUMMARY.py)** - Quick summary (executable)

#### Phase 4 (pre): Affective Space (NEW - February 2026)
- **[Phase_4_Affective_Space_Spec.md](Phase_4_Affective_Space_Spec.en.md)** - Formal specification

#### Phase 5: EDPC (NEW - March 2026)
- **[spec_phase5_edpc.md](spec_phase5_edpc.en.md)** - Experience-Driven Predictive Consolidation specification
- **[Phase_5_0_1_Value_Layer_RU_Spec.md](Phase_5_0_1_Value_Layer_RU_Spec.en.md)** - Value Layer baseline
- **[spec_semantic_similarity_replacement.md](spec_semantic_similarity_replacement.en.md)** - Deterministic semantic hashing for state similarity
- **[Phase_5_A_1_BG_Sleep_Replay_RU_Spec.md](Phase_5_A_1_BG_Sleep_Replay_RU_Spec.en.md)** - Sleep replay baseline

### Testing and Development
- **[TESTING.en.md](TESTING.en.md)** - Testing guide
- **[DEVELOPMENT.md](DEVELOPMENT.en.md)** - Development guide
- **[CHANGELOG.md](CHANGELOG.en.md)** - Project changelog

### API Reference
- **[API.md](API.en.md)** - Complete API documentation

### Reports and Status
- **[PROJECT_STATUS_FINAL.en.md](PROJECT_STATUS_FINAL.en.md)** - Current project status
- **[PROJECT_STATISTICS.md](PROJECT_STATISTICS.en.md)** - Project metrics and statistics
- **[PROJECT_PROGRESS.md](PROJECT_PROGRESS.en.md)** - Development progress

---

## Quick Navigation by Role

### For New Developers
1. Read [START_HERE.md](START_HERE.en.md)
2. Review [ARCHITECTURE.md](ARCHITECTURE.en.md)
3. Follow [INSTALLATION.en.md](INSTALLATION.en.md)
4. Check [QUICK_START_RU.md](QUICK_START_RU.en.md)
5. Explore [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.en.md)

### For System Architects
1. Review [ARCHITECTURE.md](ARCHITECTURE.en.md)
2. Study [EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.en.md)
3. Check [Phase_3_Basal_Ganglia_Action_Gating_refactoring.md](Phase_3_Basal_Ganglia_Action_Gating_refactoring.en.md)
4. Review [API.md](API.en.md)

### For QA / Testers
1. Read [TESTING.en.md](TESTING.en.md)
2. Review [PROJECT_STATISTICS.md](PROJECT_STATISTICS.en.md)
3. Check [FULL_PROJECT_TEST_REPORT.md](FULL_PROJECT_TEST_REPORT.en.md)

### For DevOps / Deployment
1. Read [INSTALLATION.en.md](INSTALLATION.en.md)
2. Review [PROJECT_STATUS_FINAL.en.md](PROJECT_STATUS_FINAL.en.md)
3. Check [DEVELOPMENT.md](DEVELOPMENT.en.md)

---

## Phase 3: Basal Ganglia (Latest Update)

### What is Phase 3?
Phase 3 implements the **Basal Ganglia Action Gating** system - a biologically plausible mechanism for action selection that includes:

- **Go/NoGo Competition**: Actions compete through competing channels
- **Neuromodulator Modulation**: Dopamine, cortisol, serotonin, norepinephrine
- **PFC Advisory**: Prefrontal cortex can suggest but not dictate
- **Two-tier plasticity**: Labile Q/Go/NoGo offsets while awake; stable values, habits, and channels consolidate in sleep
- **Habit Strength**: Learned behaviors influence future selections

### Key Documents
- [Phase_3_Basal_Ganglia_Action_Gating_refactoring.md](Phase_3_Basal_Ganglia_Action_Gating_refactoring.en.md) - Specification
- [REFACTORING_REPORT.md](../REFACTORING_REPORT.md) - Complete implementation report
- [FINAL_RESULT.txt](../FINAL_RESULT.txt) - Quick summary

### Test Results
- **29/29** Phase 3 tests passed
- **584 passed, 3 skipped** total project tests passed
- **0** test failures
- **100%** specification compliance

---

## System Components

### Core Classes
```
src/
├── agent.py                 # Main agent class
├── affect.py               # AffectiveState
├── neuromodulators.py      # NeuromodulatorState
├── wakefulness.py          # WakefulnessState
├── basal_ganglia.py        # Phase 3 - BG system
├── affective_space.py      # Phase 4 - Canonical Affective Core
├── memory.py               # Memory systems
├── intent_memory.py        # Intent-based memory
└── gui.py                  # GUI visualization
```

### Test Suite
```
tests/
├── test_affect.py
├── test_neuromodulators.py
├── test_wakefulness.py
├── test_basal_ganglia.py   # Phase 3 tests (29 tests)
├── test_affective_space.py # Phase 4 core tests
├── test_phase_5_edpc.py    # Phase 5 EDPC tests
├── test_agent.py
└── ... (500+ total tests)
```

---

## Getting Started (Quick)

### Install
```bash
# Clone repository
git clone https://github.com/burlakovmb/NOWA-Cognitive.git
cd NOWA-Cognitive

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -q
```

### Run Demo
```bash
python basal_ganglia_demo.py
```

### Use in Code
```python
from src.agent import Agent

agent = Agent()
agent.register_action_channel("attack", go_weight=0.8, nogo_weight=0.2)
action = agent.choose_action_via_basal_ganglia(pfc_pressure=1.0)
agent.record_action_outcome(action, success=True, dopamine=1.5)
agent.sleep()  # Consolidate learning
```

---

## Project Statistics

| Metric | Value |
|--------|-------|
| **Total Tests** | 507 (504 passed, 3 skipped) |
| **Pass Rate** | 100% |
| **Python Version** | 3.13+ |
| **Main Classes** | 20+ |
| **Phases Completed** | 19 |
| **Documentation Files** | 70+ |

---

## Latest Changes (Phase 5 EDPC update - Mar 3, 2026)

### EDPC Integrated
- `ValueLayer` now tracks expectation memory per encoded state
  (`expected_reward_mean/var`, `confirmation_count`, `confidence_score`, `stability_score`)
- Selective plasticity is applied via EDPC effective alpha damping
- Prediction shock is detected and propagated to replay/stress signals
- Sleep replay priority includes EDPC factors (shock + expectation stability)
- Runtime metrics include:
  - confidence/stability distributions
  - shock frequency
  - replay diversity index
  - effective alpha trajectory

### Spec Reference
See `Docs/spec_phase5_edpc.md` and updated `Docs/API.md`, `Docs/ARCHITECTURE_UPDATED.md`.

---

## Support and Contribution

For issues, questions, or contributions:
1. Check [DEVELOPMENT.md](DEVELOPMENT.en.md)
2. Review [TESTING.en.md](TESTING.en.md)
3. See [CHANGELOG.md](CHANGELOG.en.md) for version info

---

## File Organization

All documentation is now organized in the `Docs/` folder:
- Core architecture and design documents
- Component-specific guides
- API reference
- Testing and development guides
- Status reports and changelogs

**Location:** `e:\git\NOWA-Cognitive\Docs\`

---

## Recommended Reading Order

1. **START_HERE.md** - Overview and introduction
2. **QUICK_START_RU.md** - Get running quickly
3. **ARCHITECTURE.md** - Understand the design
4. **Phase_3_Basal_Ganglia_Action_Gating_refactoring.md** - Latest feature
5. **API.md** - Programming reference
6. **TESTING.en.md** - How to test
7. **DEVELOPMENT.md** - Contributing guide

---

**Last Updated:** 2026-03-03  
**Version:** 3.3  
**Status:** Production Ready (EDPC integrated)
