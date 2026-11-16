# NOWA-Cognitive Project Documentation

Russian version: [00_INDEX_NEW.ru.md](00_INDEX_NEW.ru.md)



**Status (27 September 2026).** This index is superseded. Reading order: [INDEX.en.md](INDEX.en.md) and [SCIENTIFIC_DESCRIPTION.en.md](SCIENTIFIC_DESCRIPTION.en.md).

**Version:** 2.2  
**Last Updated:** February 2026  
**Status:** Production Ready - Phase 3 Complete

---

## 📚 Documentation Structure

### 🚀 Getting Started

- **[START_HERE.md](START_HERE.en.md)** - Bilingual entry point (English/Russian) - UPDATED
- **[QUICK_START.md](QUICK_START.en.md)** - Get running in 5 minutes (English) - ✨NEW
- **[QUICK_START_RU.md](QUICK_START_RU.en.md)** - Quick start guide (Russian)
- **[INSTALLATION.en.md](INSTALLATION.en.md)** - Installation and setup instructions

### 🏗️ Architecture & Design

- **[ARCHITECTURE.md](ARCHITECTURE.en.md)** - Overall system architecture
- **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.en.md)** - Complete developer guide with examples - ✨NEW  
- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.en.md)** - Project folder structure
- **[EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.en.md)** - High-level overview of the system

### 📖 Core Components

#### Phase 1: Foundation
- Affective System (AffectiveState)
- Neuromodulator System (NeuromodulatorState)
- Basic action generation

#### Phase 2: Advanced Features
- **[README_AFFECTIVE_SYSTEM.md](README_AFFECTIVE_SYSTEM.en.md)** - Affective regulation
- **[Phase2_Wakefulness_PFC_Extension.md](Phase2_Wakefulness_PFC_Extension.en.md)** - Wakefulness and PFC
- **[spec_circadian_process_c.md](spec_circadian_process_c.en.md)** - Circadian Process C for wakefulness model
- **[NEUROMODULATORS_QUICK_REFERENCE.md](NEUROMODULATORS_QUICK_REFERENCE.en.md)** - Neuromodulator reference

#### Phase 3: Basal Ganglia (February 2026) ✨
- **[PHASE_3_GUIDE.md](PHASE_3_GUIDE.en.md)** - Comprehensive Phase 3 guide - ✨NEW
- **[Phase_3_Basal_Ganglia_Action_Gating_refactoring.md](Phase_3_Basal_Ganglia_Action_Gating_refactoring.en.md)** - BG specification
- **[REFACTORING_REPORT.md](../REFACTORING_REPORT.md)** - Complete refactoring report
- **[REFACTORING_SUMMARY.py](../REFACTORING_SUMMARY.py)** - Quick summary (executable)

### 🧪 Testing & Development
- **[TESTING.en.md](TESTING.en.md)** - Testing guide
- **[DEVELOPMENT.md](DEVELOPMENT.en.md)** - Development guide
- **[CHANGELOG.md](CHANGELOG.en.md)** - Project changelog

### 📋 API Reference
- **[API.md](API.en.md)** - Complete API documentation

### 📊 Reports & Status
- **[PROJECT_STATUS_FINAL.en.md](PROJECT_STATUS_FINAL.en.md)** - Current project status
- **[PROJECT_STATISTICS.md](PROJECT_STATISTICS.en.md)** - Project metrics and statistics
- **[PROJECT_PROGRESS.md](PROJECT_PROGRESS.en.md)** - Development progress

---

## 🎯 Quick Navigation by Role

### For New Developers
1. Read [START_HERE.md](START_HERE.en.md) - Updated with bilingual content
2. Try [QUICK_START.md](QUICK_START.en.md) - Get running in 5 minutes
3. Read [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.en.md) - Comprehensive guide
4. Review [ARCHITECTURE.md](ARCHITECTURE.en.md)
5. Study [PHASE_3_GUIDE.md](PHASE_3_GUIDE.en.md)

### For System Architects
1. Review [ARCHITECTURE.md](ARCHITECTURE.en.md)
2. Study [EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.en.md)
3. Check [PHASE_3_GUIDE.md](PHASE_3_GUIDE.en.md)
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

## 🔗 Phase 3: Basal Ganglia (Latest - February 2026)

### What is Phase 3?
Phase 3 implements the **Basal Ganglia Action Gating** system - a biologically plausible mechanism for action selection that includes:

- **Go/NoGo Competition**: Actions compete through competing channels
- **Neuromodulator Modulation**: Dopamine, cortisol, serotonin, norepinephrine
- **PFC Advisory**: Prefrontal cortex can suggest but not dictate
- **Two-tier plasticity**: Labile Q/Go/NoGo offsets while awake; stable values, habits, and channels consolidate in sleep
- **Habit Strength**: Learned behaviors influence future selections (weight: ×0.3)

### Key Documents
- [QUICK_START.md](QUICK_START.en.md) - Get started in 5 minutes
- [PHASE_3_GUIDE.md](PHASE_3_GUIDE.en.md) - Comprehensive Phase 3 guide - ✨NEW
- [Phase_3_Basal_Ganglia_Action_Gating_refactoring.md](Phase_3_Basal_Ganglia_Action_Gating_refactoring.en.md) - Specification
- [REFACTORING_REPORT.md](../REFACTORING_REPORT.md) - Complete implementation report
- [FINAL_RESULT.txt](../FINAL_RESULT.txt) - Quick summary

### Test Results
✅ **29/29** Phase 3 tests PASSED  
✅ **279/279** Total project tests PASSED  
✅ **0** test failures  
✅ **100%** specification compliance  

### Key Formula
```
Net = Go - 0.5×NoGo + PFC_pressure + habit_strength×0.3

Where:
- Go = go_weight × dopamine × (1 + norepinephrine)
- NoGo = nogo_weight × cortisol
- PFC_pressure = prefrontal cortex advisory signal
- habit_strength = learned behavior strength (0-1)
```

---

## 📦 System Components

### Core Classes
```
src/
├── agent.py                 # Main agent class
├── affect.py               # AffectiveState
├── neuromodulators.py      # NeuromodulatorState
├── wakefulness.py          # WakefulnessState
├── basal_ganglia.py        # Phase 3 - BG system (600+ lines)
├── memory.py               # Memory systems
├── intent_memory.py        # Intent-based memory
└── gui.py                  # GUI visualization
```

### Test Suite
```
tests/
├── test_basal_ganglia.py   # Phase 3 tests (29 tests) ✅
├── test_agent.py           # Agent integration
├── test_affect.py
├── test_neuromodulators.py
├── test_wakefulness.py
└── ... (250+ total tests)
```

---

## 🚀 Getting Started (Quick)

### Install
```bash
# Navigate to project
cd e:\git\NOWA-Cognitive

# Install dependencies
pip install -r requirements.txt

# Verify installation
pytest tests/ -q
# Expected: 279 passed in ~1.5s ✅
```

### Run GUI Demo
```bash
python src/gui.py
```

### Write Your First Program
```python
from src.agent import Agent

# Create agent
agent = Agent(agent_name="MyBot")

# Register actions
agent.register_action_channel("attack", go_weight=0.8, nogo_weight=0.2)
agent.register_action_channel("defend", go_weight=0.5, nogo_weight=0.5)

# Let Basal Ganglia choose
action = agent.choose_action_via_basal_ganglia(pfc_pressure=1.0)
print(f"Agent chose: {action}")

# Record outcome and learn
agent.record_action_outcome(action, success=True, dopamine=1.5)

# Sleep to consolidate learning
agent.sleep()
```

See [QUICK_START.md](QUICK_START.en.md) for more examples.

---

## 📊 Project Statistics

| Metric | Value |
|--------|-------|
| **Total Tests** | 279 |
| **Phase 3 Tests** | 29 |
| **Pass Rate** | 100% ✅ |
| **Test Failures** | 0 |
| **Python Version** | 3.13+ |
| **Main Classes** | 20+ |
| **Phases Completed** | 3 |
| **Documentation Files** | 70+ |
| **Lines of Code** | 5,000+ |

---

## 🔄 Latest Changes (Phase 3 - Feb 2026)

### Refactoring Completed ✅
- ✅ Added `habit_strength` to action selection formula
- ✅ Updated BG tests for stability and robustness
- ✅ Comprehensive new documentation
- ✅ 100% specification compliance
- ✅ Zero regressions (279/279 tests pass)

### New Documentation
- ✅ [START_HERE.md](START_HERE.en.md) - Updated to bilingual
- ✅ [QUICK_START.md](QUICK_START.en.md) - 5-minute quick start
- ✅ [PHASE_3_GUIDE.md](PHASE_3_GUIDE.en.md) - Comprehensive Phase 3 guide
- ✅ [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.en.md) - Developer reference
- ✅ [00_INDEX.md](00_INDEX.en.md) - Updated navigation index

### Formula Updated
```python
# Before (Phase 2):
Net = Go - 0.5*NoGo + PFC_pressure*wake_mod

# After (Phase 3 - with habit integration):
Net = Go - 0.5*NoGo + PFC_pressure*wake_mod + habit_strength*0.3
```

---

## 📞 Support & Contribution

For issues, questions, or contributions:
1. Check [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.en.md)
2. Review [TESTING.en.md](TESTING.en.md)
3. See [DEVELOPMENT.md](DEVELOPMENT.en.md)
4. Check [CHANGELOG.md](CHANGELOG.en.md)

---

## 📄 File Organization

All documentation is organized in the `Docs/` folder:
- Core architecture and design documents
- Component-specific guides
- API reference
- Testing and development guides
- Status reports and changelogs

**Location:** `e:\git\NOWA-Cognitive\Docs\`

---

## ✨ Recommended Reading Order

### Quick Path (30 minutes)
1. **[START_HERE.md](START_HERE.en.md)** - Overview (5 min)
2. **[QUICK_START.md](QUICK_START.en.md)** - Get running (5 min)
3. **Run GUI** - See it work (5 min)
4. **[PHASE_3_GUIDE.md](PHASE_3_GUIDE.en.md)** - Learn Phase 3 (15 min)

### Complete Path (2+ hours)
1. **[START_HERE.md](START_HERE.en.md)** - Overview and introduction
2. **[QUICK_START.md](QUICK_START.en.md)** - Get running quickly
3. **[PHASE_3_GUIDE.md](PHASE_3_GUIDE.en.md)** - Latest feature details
4. **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.en.md)** - Developer reference
5. **[ARCHITECTURE.md](ARCHITECTURE.en.md)** - Understand the design
6. **[API.md](API.en.md)** - Programming reference
7. **[TESTING.en.md](TESTING.en.md)** - How to test
8. **[DEVELOPMENT.md](DEVELOPMENT.en.md)** - Contributing guide

---

## 🎯 Key Documents by Purpose

### "I want to understand the system" (45 min)
1. [ARCHITECTURE.md](ARCHITECTURE.en.md) - System design
2. [PHASE_3_GUIDE.md](PHASE_3_GUIDE.en.md) - Phase 3 details
3. [API.md](API.en.md) - API reference

### "I want to write code" (2 hours)
1. [QUICK_START.md](QUICK_START.en.md) - Get started
2. [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.en.md) - Guide with examples
3. Source code in `src/`
4. Tests in `tests/`

### "I want to extend the system" (3+ hours)
1. [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.en.md) - Complete guide
2. [ARCHITECTURE.md](ARCHITECTURE.en.md) - System design
3. [PHASE_3_GUIDE.md](PHASE_3_GUIDE.en.md) - Phase 3 details
4. Read and study source code
5. Write tests (see [TESTING.en.md](TESTING.en.md))

### "I need to verify everything works"
1. [PROJECT_STATUS_FINAL.en.md](PROJECT_STATUS_FINAL.en.md) - Status report
2. [PROJECT_STATISTICS.md](PROJECT_STATISTICS.en.md) - Test statistics
3. Run: `pytest tests/ -q` - All 279 tests should pass

---

## 🚀 Next Steps (Choose One)

### 👀 See it Work Immediately
```bash
python src/gui.py
```
Estimated time: 2 minutes

### 💻 Write Code
Follow [QUICK_START.md](QUICK_START.en.md)  
Estimated time: 5 minutes

### 📖 Learn Properly
Follow "Complete Path" above  
Estimated time: 2+ hours

### 🎓 Deep Understanding
1. Complete Path
2. Read source code in `src/`
3. Review all tests in `tests/`
Estimated time: 4+ hours

---

## ✅ Verification Checklist

Make sure you can:
- [ ] Run: `pytest tests/ -q` → shows 279 passed ✅
- [ ] Run: `python src/gui.py` → GUI opens
- [ ] Understand: [QUICK_START.md](QUICK_START.en.md) examples
- [ ] Code: Write your first agent (follow QUICK_START)
- [ ] Know: Where all documentation is located

---

**Last Updated:** February 2026  
**Version:** 2.2  
**Status:** ✅ Production Ready - Phase 3 Complete

All development complete. System fully documented and tested.
