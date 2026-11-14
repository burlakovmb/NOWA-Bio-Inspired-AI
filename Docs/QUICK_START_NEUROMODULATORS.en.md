# Quick Reference — Neuromodulators (February 2026)

Russian version: [QUICK_START_NEUROMODULATORS.ru.md](QUICK_START_NEUROMODULATORS.ru.md)

**Status (27 September 2026).** A core document. The current scientific exposition of the complex, in Russian and in English, is [SCIENTIFIC_DESCRIPTION.en.md](SCIENTIFIC_DESCRIPTION.en.md). The text below retains the wording of its original drafting: a normative module contract or a laboratory record.


**Checklist for new developers**

---

## In Five Minutes

### What is it?
A system of four global regulators (DA, NE, 5-HT, CORT) that modulate the agent's learning.

### Where is it?
- Code: `src/neuromodulators.py`
- Graphical interface: side panel, lines "DA: 0.XX", "NE: 0.XX", and so on
- Documentation: `Docs/NEUROMODULATORS_*.md`

### How does it work?
1. **Step:** reward, novelty, and conflict update the neuromodulators
2. **Sleep:** sleep activates the effects (strengthening of patterns, chains, forgetting)

### Principal parameters
| Neuromodulator | Baseline | Maximum | Coefficient |
|---|---|---|---|
| DA | 0.1 | 1.0 | 0.2 * reward |
| NE | 0.1 | 1.0 | 0.3 * novelty |
| 5-HT | 0.1 | 1.0 | +0.01 (stability) |
| CORT | 0.05 | 1.0 | 0.15 * conflict |

---

## In Thirty Minutes

### Read in this order
1. [NEUROMODULATORS_QUICK_REFERENCE.md](NEUROMODULATORS_QUICK_REFERENCE.en.md) — 15 min
2. Run `python src/gui.py` — 10 min
3. Review the examples in the document — 5 min

### Key concepts
- All values are normalized to [0.0, 1.0]
- Decay occurs automatically
- Effects are applied only during sleep
- The state is saved with the agent (save/load)

---

## In Sixty Minutes (for developers)

### Files to study
1. `src/neuromodulators.py` — class `NeuromodulatorState` (81 lines)
2. `src/agent.py` — integration (search "neuromodulators")
3. `src/sleep.py` — effects (method `_apply_neuromodulators_during_sleep`)
4. `tests/test_neuromodulators.py` — usage examples

### How to extend
```python
# Добавить новый нейромодулятор:
# 1. Добавить поле в __init__
# 2. Добавить логику в update_from_signals()
# 3. Добавить эффект в sleep.py
# 4. Добавить тест в test_neuromodulators.py
```

The comments in the fragment above state the four steps: add a field in `__init__`, add logic in `update_from_signals()`, add an effect in `sleep.py`, and add a test in `test_neuromodulators.py`.

---

## Commands for a quick start

```bash
# Запустить GUI с нейромодуляторами
python src/gui.py

# Запустить тесты
pytest tests/test_neuromodulators.py -v

# Проверить всё работает
python -c "
from src.agent import Agent
from src.neuromodulators import NeuromodulatorState
nm = NeuromodulatorState()
nm.update_from_signals(reward=0.5, novelty=0, conflict=0)
print('DA:', nm.dopamine)
print('OK!')
"

# See the dict shape used inside a .nowa save
python -c "
from neuromodulators import NeuromodulatorState
nm = NeuromodulatorState()
print(nm.to_dict())
"
```

The commands launch the graphical interface with neuromodulators, run the tests, construct a `NeuromodulatorState`, update it from a reward of `0.5`, print dopamine, and print the dictionary form used for persistence.

---

## Statistics

| Metric | Value |
|---|---|
| New files | 1 (`neuromodulators.py`) |
| Files modified | 5 |
| New tests | 4 |
| Tests in total | 172/172 passing |
| Documentation | about 1300 lines |
| Code | about 194 lines |

---

## Frequently asked questions

**Q: Why four neuromodulators?**  
A: DA (success), NE (novelty), 5-HT (stability), and CORT (stress) cover the principal scenarios.

**Q: Does this affect action selection?**  
A: No, only memory consolidation. This preserves "physics without psychology".

**Q: What if the neuromodulators are disabled?**  
A: The system works as before (backward compatibility).

**Q: How is a new neuromodulator added?**  
A: See the extension section in NEUROMODULATORS_IMPLEMENTATION.md

**Q: Where are they stored?**  
A: In `agent_state['neuromodulators']` when the agent is saved.

---

## Documents by purpose

| Need | Document | Time |
|---|---|---|
| Quick reference | NEUROMODULATORS_QUICK_REFERENCE.md | 10 min |
| Full information | NEUROMODULATORS_IMPLEMENTATION.md | 30 min |
| Report | NEUROMODULATORS_FULL_REPORT.md | 45 min |
| Overview | NEUROMODULATORS_SUMMARY_REPORT.md | 20 min |
| How to read | NEUROMODULATORS_DOCUMENTATION_GUIDE.md | 15 min |
| Checklist | NEUROMODULATORS_CHECKLIST.md | 10 min |

---

## Learning

### Level 1: User (understanding)
- [ ] I know what neuromodulators are
- [ ] I know the four types
- [ ] I see them in the graphical interface

**Time:** 10 minutes

### Level 2: Developer (use)
- [ ] I know how they are updated
- [ ] I know how they affect memory
- [ ] I can read the code

**Time:** 45 minutes plus practice

### Level 3: Architect (extension)
- [ ] I know the internal structure
- [ ] I can add a new modulator
- [ ] I can optimize

**Time:** 2 hours or more, plus design

---

## If something does not work

### Neuromodulators are not shown in the graphical interface
- [ ] Was `python src/gui.py` started?
- [ ] Were several steps tried?
- [ ] Values must be greater than 0.05 to be visible

### Tests do not pass
- [ ] Was `pytest tests/test_neuromodulators.py -v` run?
- [ ] Are all dependencies installed?
- [ ] Check requirements.txt

### I do not know how something works
- [ ] See the examples in QUICK_REFERENCE.md
- [ ] Read the comments in the code
- [ ] See the tests: they show usage

---

## Final checklist

Before the first use:
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Tests run: `pytest tests/test_neuromodulators.py`
- [ ] Graphical interface started: `python src/gui.py`
- [ ] QUICK_REFERENCE.md read
- [ ] The four types of neuromodulators are understood

The reader is ready to work.

---

**Document:** quick reference  
**Date:** 5 February 2026  
**Version:** 1.0  

Questions are answered by the documentation and by the source code.
