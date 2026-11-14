# Update: Saving and Loading Agent State

Russian version: [SAVE_LOAD_AFFECT_STATE.ru.md](SAVE_LOAD_AFFECT_STATE.ru.md)

**Status (27 September 2026).** A core document. The current scientific exposition of the complex, in Russian and in English, is [SCIENTIFIC_DESCRIPTION.en.md](SCIENTIFIC_DESCRIPTION.en.md). The text below retains the wording of its original drafting: a normative module contract or a laboratory record.


**Date**: 8 February 2026  
**Status**: COMPLETED AND TESTED

---

## What was added

Full support was implemented for saving and loading:
- affective state
- affective traces (Phase 3.5)
- neuromodulators
- agent lifetime

---

## Changes made

### 1. **src/storage.py** — update of the save and load functions

#### Import added
```python
from affect import AffectiveState
```

#### Function `save_agent()` — now saves affect_state, traces, and lifetime
```python
def save_agent(self, hippocampus, cortex, selector, affect_state=None,
               temporal=None, sleep_manager=None, neuromodulators=None,
               affective_persistence=None, filename=None, agent=None):
    """Save the agent state to a file"""
    # ... existing code ...
    
    # Save the affective state if it is present
    if affect_state is not None:
        agent_state["affect_state"] = {
            "valence": affect_state.valence,
            "arousal": affect_state.arousal,
            "threat": affect_state.threat,
            "curiosity": affect_state.curiosity
        }

    # New: save affective traces (Phase 3.5)
    if affective_persistence is not None:
        agent_state["affective_persistence"] = affective_persistence.to_dict()

    # New: save the agent lifetime
    if agent is not None:
        agent_state["agent_lifetime"] = {
            "created_ts": agent.created_ts,
            "simulated_sleep_seconds": agent._simulated_sleep_seconds
        }
```

**Changes**:
- Parameter `affect_state=None` added
- Parameter `affective_persistence=None` added
- Parameter `agent=None` added
- All 4 affective-state parameters are saved
- Backward compatibility is preserved (the parameter is optional)

#### Function `load_agent()` — now loads affect_state, traces, and lifetime
```python
def load_agent(self, hippocampus, cortex, selector, filepath, affect_state=None,
               temporal=None, sleep_manager=None, affective_persistence=None, agent=None):
    """Load the agent state from a file"""
    # ... existing code ...
    
    # Restore the affective state if it was saved
    if affect_state is not None and "affect_state" in agent_state:
        affect_data = agent_state["affect_state"]
        affect_state.valence = affect_data["valence"]
        affect_state.arousal = affect_data["arousal"]
        affect_state.threat = affect_data["threat"]
        affect_state.curiosity = affect_data["curiosity"]

    # New: restore affective traces
    if affective_persistence is not None and "affective_persistence" in agent_state:
        affective_persistence.from_dict(agent_state["affective_persistence"])

    # New: restore the agent lifetime
    if agent is not None and "agent_lifetime" in agent_state:
        agent.created_ts = agent_state["agent_lifetime"]["created_ts"]
        agent._simulated_sleep_seconds = agent_state["agent_lifetime"]["simulated_sleep_seconds"]
```

**Changes**:
- Parameter `affect_state=None` added
- Parameter `affective_persistence=None` added
- Parameter `agent=None` added
- All 4 affective-state parameters are restored
- Backward compatibility is preserved (the parameter is optional)

### 2. **src/gui.py** — update of the interface calls

#### Function `save_state()` — now passes affect_state, traces, and agent
```python
def save_state(self):
    """Save the agent state"""
    try:
        filepath = self.storage.save_agent(
            self.hippocampus,
            self.cortex,
            self.selector,
            affect_state=self.agent.affect_state,          # ← save affect
            affective_persistence=self.agent.affective_persistence,  # ← traces
            agent=self.agent  # ← lifetime
        )
```

#### Function `load_state()` — now loads affect_state, traces, and agent
```python
def load_selected():
    # ...
    timestamp = self.storage.load_agent(
        self.hippocampus,
        self.cortex,
        self.selector,
        selected_save['path'],
        affect_state=self.agent.affect_state,           # ← affect
        affective_persistence=self.agent.affective_persistence,  # ← traces
        agent=self.agent  # ← lifetime
    )
    # ...
    self.update_affect_display()  # ← Update the visualization
```

---

## Testing

A new file `test_save_load_affect.py` was created with 8 tests:

### Test results

```
Test 1: Initial affective state
   - Check of parameter initialization

Test 2: Update of affective state
   - Check of update_from_reward() and update_from_novelty()

Test 3: Saving state with affect_state
   - Check that a file with affective parameters is created

Test 4: Changing state before loading
   - Check that valence is changed successfully

Test 5: Loading state with affect_state restored
   - Check that values are restored

Test 6: Check of restoration correctness
   - Check of the accuracy of restoration of all parameters

Test 7: Loading into the original agent.affect_state
   - Check of restoration into agent.affect_state

Test 8: Loading without affect_state (backward compatibility)
   - Check that the old API still works

Result: ALL 8 TESTS PASSED

New tests added:
- `tests/test_affective_persistence.py`
- `tests/test_agent_lifetime_save_load.py`
```

### All existing tests still pass

```
test_affective_regulators.py: 25/25 PASSED
test_affect_integration.py: 12/12 PASSED
─────────────────────────────────────
TOTAL: 37/37 PASSED
```

---

## Save and load process

### Saving

```
The user presses "Save state"
        ↓
GUI.save_state() calls storage.save_agent()
        ↓
storage.save_agent() saves:
  ├─ hippocampus.experiences
  ├─ cortex.patterns
  ├─ selector.actions & confidence_threshold
  └─ affect_state (valence, arousal, threat, curiosity) ← NEW
  ├─ affective_persistence (traces) ← NEW
  └─ agent_lifetime (created_ts, simulated_sleep_seconds) ← NEW
        ↓
The file is saved as UTF-8 JSON (`nowa-agent-state`, schema version `1`, `.nowa`). Pickle is not used; legacy `.pkl` files are rejected.
        ↓
The interface shows: "State saved"
```

### Loading

```
The user selects a file and presses "Load"
        ↓
GUI.load_state() calls storage.load_agent()
        ↓
storage.load_agent() restores:
  ├─ hippocampus.experiences
  ├─ cortex.patterns
  ├─ selector.actions & confidence_threshold
  └─ affect_state (valence, arousal, threat, curiosity) ← NEW
  ├─ affective_persistence (traces) ← NEW
  └─ agent_lifetime (created_ts, simulated_sleep_seconds) ← NEW
        ↓
The interface calls update_affect_display()
        ↓
The visualization is updated with the loaded values
        ↓
The interface shows: "State loaded"
```

---

## Checklist

- [x] `save_agent()` saves affect_state
- [x] `load_agent()` loads affect_state
- [x] The interface passes affect_state on save
- [x] The interface passes affect_state on load
- [x] The interface passes affective_persistence on save
- [x] The interface passes affective_persistence on load
- [x] The interface passes agent on save and load
- [x] The interface updates the visualization after loading
- [x] Backward compatibility is preserved
- [x] All 8 new tests pass
- [x] All 37 existing tests pass
- [x] There are no regressions

---

## Statistics

```
Files changed:      2
  ├─ src/storage.py (parameters added + lifetime)
  └─ src/gui.py (save/load calls updated)

Files created:      1
  └─ test_agent_lifetime_save_load.py (new test)

New tests:          2 (affective persistence + lifetime)

Regressions:        0
```

---

## Result

When an agent is saved:
- Affective state is saved
- Affective traces are saved
- Agent lifetime is saved
- On load, the state is restored
- The interface visualization updates correctly
- Backward compatibility is preserved
- The change is fully tested

**Status**: **READY FOR USE**

---

## How to use

### In the interface
1. Press "Save" and affect_state is saved
2. Press "Load" and affect_state is loaded
3. The visualization updates automatically

### Programmatically
```python
# Saving
storage.save_agent(
    hippocampus, cortex, selector,
    affect_state=agent.affect_state,
    affective_persistence=agent.affective_persistence,
    agent=agent
)

# Loading
storage.load_agent(
    hippocampus, cortex, selector, filepath,
    affect_state=agent.affect_state,
    affective_persistence=agent.affective_persistence,
    agent=agent
)
```

---

**Date of update**: 8 February 2026  
**Version**: 1.2  
**Status**: PRODUCTION READY
