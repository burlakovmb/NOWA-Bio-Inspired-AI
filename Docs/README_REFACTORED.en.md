# NOWA-Cognitive: Refactored Architecture

Russian version: [README_REFACTORED.ru.md](README_REFACTORED.ru.md)

**Status (27 September 2026).** A core document. The current scientific exposition of the complex, in Russian and in English, is [SCIENTIFIC_DESCRIPTION.en.md](SCIENTIFIC_DESCRIPTION.en.md). The text below retains the wording of its original drafting: a normative module contract or a laboratory record.

## Overview

NOWA-Cognitive has been successfully refactored to implement the core principle:

> **Behavior is not learned. It emerges from experience and consolidation.**

This is NOT a machine learning system. It's a cognitive architecture where:
- Experiences are immutable historical records
- Waking writes a bounded labile layer; stable memory consolidates only in sleep
- Behavior emerges from memory activation, not weight optimization
- The agent adapts through labile tags by day and consolidation by night

---

## System Components

### 1. **Event & Experience**
Immutable representations of what happens:

```python
# Create context
path = Path()
path = path.add_event(Event("user:hello", EventType.CONTEXT))
path = path.add_event(Event("action:greet", EventType.ACTION))

# Store as immutable experience
exp = Experience(path, consequence=result_event, intensity=1.0)
# Cannot modify exp.path after creation - it's frozen!
```

### 2. **Hippocampus** (Short-term Memory)
Stores recent experiences with time-based decay:

```python
hippocampus = NOWAHippocampus()

# Store experience
hippocampus.store(path, consequence=event, intensity=1.0)

# Reinforce same pattern (increases reinforcement_count)
hippocampus.reinforce(path)

# Get active experiences in context
active_exps = hippocampus.activate(["user:hello"])

# Get candidates for sleep consolidation
candidates = hippocampus.get_candidates_for_sleep(min_reinforcement=2)
```

### 3. **Selector** (Action Choice - Non-Learnable)
Makes decisions based on experience pressure, NOT weights:

```python
selector = ActionSelector(["greet", "ignore", "ask"], confidence_threshold=0.7)

# Choose action based on hippocampal and cortical input
# (selector has NO weights, NO learning, NO optimization)
action = selector.choose(hippocampal_exps, cortical_patterns)
```

**How selection works:**
1. Calculate "pressure" from hippocampal experience intensity
2. Add bias from cortical patterns
3. Compute confidence = max_pressure / total_pressure
4. If confidence > threshold: deterministic choice (best option)
5. If confidence ≤ threshold: stochastic choice (explore)

### 4. **Sleep Manager** (stable-tier consolidation)
Consolidates experiences to abstract patterns:

```python
sleep_manager = SleepManager(hippocampus, cortex)

# Consolidation cycle:
# 1. Replay experiences to strengthen
# 2. Cluster similar experiences
# 3. Abstract into cortical patterns
# 4. Forget unstable traces
stats = sleep_manager.sleep_cycle()

# Multiple deep sleep cycles
stats = sleep_manager.deep_sleep(cycles=3)
```

### 5. **Cortex** (Long-term Memory)
Slow memory of abstract patterns - ONLY modified during sleep:

```python
from sleep import CortexMemory

cortex = CortexMemory()

# Patterns stored during sleep consolidation (not during waking!)
pattern = cortex.store_pattern(("context", "action:greet"))

# Activate patterns in context
active_patterns = cortex.activate(["user:hello"])
```

### 6. **Agent** (The System)
Integrates all components:

```python
agent = Agent(hippocampus, cortex, selector, sleep_manager=sleep_manager)

# Waking: episodes + labile Q/Go/NoGo offsets when reward is known
action = agent.step(["user:hello"], consequence=result_event, intensity=1.0)

# Sleep: stable Q, channels, habits, cortex
stats = agent.sleep(cycles=3)

# Check current state
state = agent.get_state()
# {
#   "hippocampus": {total_experiences: 42, avg_reinforcement: 2.1, ...},
#   "cortex": {total_patterns: 8, avg_strength: 0.75, ...},
#   "sleep_cycles": 5
# }
```

---

## Example: Complete Wake-Sleep-Wake Cycle

```python
from src.hippocampus import NOWAHippocampus
from src.cortex import CortexMemory
from src.selector import ActionSelector
from src.sleep import SleepManager
from src.agent import Agent
from src.experience import Event, Path, EventType

# Initialize
hippocampus = NOWAHippocampus()
cortex = CortexMemory()
selector = ActionSelector(["respond", "ignore", "question"])
sleep_manager = SleepManager(hippocampus, cortex)
agent = Agent(hippocampus, cortex, selector, sleep_manager)

print("=== WAKING: Interact ===")
for i in range(10):
    # Agent experiences context and acts
    action = agent.step(["user:hello"])
    print(f"Step {i}: {action}")

print("\n=== SLEEPING: Consolidate ===")
# Sleep consolidates experiences to patterns
stats = agent.sleep(cycles=3)
print(f"Sleep stats: {stats}")

print("\n=== WAKING: Behavior changed ===")
for i in range(5):
    # Behavior emerges from consolidated patterns
    action = agent.step(["user:hello"])
    print(f"Step {i}: {action}")

print("\n=== STATE ===")
state = agent.get_state()
print(f"Hippocampus: {state['hippocampus']}")
print(f"Cortex: {state['cortex']}")
print(f"Sleep cycles: {state['sleep_cycles']}")
```

---

## Key Principles

### What's Allowed
- Storing experiences (immutable)
- Time-based decay of activation energy
- Context-based experience activation
- Sleep consolidation of patterns
- Confidence-based selection with stochasticity
- Natural forgetting of unstable memories

### What's Forbidden
- Optimizing selector weights
- Calculating loss/accuracy
- Training epochs
- Reward accumulation
- Direct behavior modification
- Any learning outside of sleep

---

## Testing

All 66 tests passing:

```bash
cd "e:\git\NOWA-Cognitive"
python -m unittest discover -s tests -p "test_*.py" -v

# Results:
# - test_experience_immutability.py: 14 tests ✅
# - test_hippocampus.py: 15 tests ✅
# - test_selector.py: 13 tests ✅
# - test_sleep_consolidation.py: 11 tests ✅
# - test_agent.py: 15 tests ✅
# - test_trainer_deprecated.py: 1 marker ✅

Ran 66 tests in 0.110s
OK
```

---

## Files Structure

```
src/
├── experience.py          # Event, Path, Experience (IMMUTABLE)
├── hippocampus.py         # Short-term memory (no optimization)
├── selector.py            # Non-learnable action selection
├── sleep.py               # Sleep consolidation (ONLY learning)
├── cortex.py              # Long-term memory (redirect to sleep)
├── agent.py               # Main system integration
├── trainer.py             # ⚠️ DEPRECATED - do not use
├── (other files...)

tests/
├── test_experience_immutability.py    # Event/Path/Experience
├── test_hippocampus.py               # Storage & activation
├── test_selector.py                  # Non-learning selection
├── test_sleep_consolidation.py       # Sleep & consolidation
├── test_agent.py                     # Integration & cycles
├── test_trainer_deprecated.py        # Deprecation marker
└── __init__.py                       # Test package
```

---

## Architecture Diagram

```
WAKING ACTIVITY
├── Context Input
├── Agent.step()
│   ├── Get active experiences (Hippocampus.activate)
│   ├── Get active patterns (Cortex.activate)
│   ├── Selector.choose() ← pressure-based, NOT optimized
│   ├── Return action
│   └── Store experience (immutable)
└── No learning happens!

↓

SLEEP
├── SleepManager.sleep_cycle()
│   ├── Replay experiences
│   ├── Cluster similar patterns
│   ├── Consolidate to cortex
│   └── Forget unstable traces
└── THIS is where learning happens!

↓

BEHAVIOR EMERGES from:
├── Hippocampal activation (recent)
├── Cortical patterns (consolidated)
└── Selection pressure (non-optimized)
```

---

## The NOWA Principle

**Question:** If the selector is frozen and the agent gets new experience, will behavior change?

**NOWA Answer:** YES, through sleep consolidation!
- New experiences activate in hippocampus
- Sleep clusters and consolidates them
- Cortical patterns shift
- Selection pressure changes
- Behavior emerges as different

**ML Answer:** Maybe. Depends on weight optimization during learning.

**This is the fundamental difference:** NOWA changes behavior through consolidation of experience, not optimization of parameters.

---

## Migration from Old Code

If you were using the old `SelectorTrainer`:

```python
# ❌ OLD WAY (REMOVED)
trainer = SelectorTrainer(selector, hippocampus, cortex)
trainer.train_full(experiences, epochs=5)

# ✅ NEW WAY
sleep_manager = SleepManager(hippocampus, cortex)
agent = Agent(hippocampus, cortex, selector, sleep_manager)

# Waking: experiences accumulate
for _ in range(100):
    agent.step(context)

# Sleep: consolidation
agent.sleep(cycles=5)

# Behavior emerges from consolidation!
```

---

## Documentation

- [REFACTORING_COMPLETE.md](REFACTORING_COMPLETE.en.md) - Detailed refactoring report
- [nowa_refactoring_plan_v_2.md](nowa_refactoring_plan_v_2.en.md) - Original refactoring plan
- [CHANGELOG.md](CHANGELOG.en.md) - Version history

---

## Future Development

The refactored architecture is now ready for:
- Natural language processing (NOWA NLP)
- Multi-agent systems
- Long-term memory studies
- Behavioral emergence research
- Cognitive modeling

All within the principle: **Behavior emerges, not learned.**

---

**Status:** Production Ready - All tests passing, architecture validated
