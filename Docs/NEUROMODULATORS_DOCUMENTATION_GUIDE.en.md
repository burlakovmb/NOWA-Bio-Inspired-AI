# Documentation Guide — Neuromodulators (February 2026)

Russian version: [NEUROMODULATORS_DOCUMENTATION_GUIDE.ru.md](NEUROMODULATORS_DOCUMENTATION_GUIDE.ru.md)

**Status (27 September 2026).** A core document. The current scientific exposition of the complex, in Russian and in English, is [SCIENTIFIC_DESCRIPTION.en.md](SCIENTIFIC_DESCRIPTION.en.md). The text below retains the wording of its original drafting: a normative module contract or a laboratory record.

**Date:** 5 February 2026
**For:** developers of NOWA-Cognitive
**Length:** about 50 minutes of reading

---

## Quick navigation

### If ten minutes are available

Read:

1. **[NEUROMODULATORS_QUICK_REFERENCE.md](NEUROMODULATORS_QUICK_REFERENCE.en.md)** — a short account of the system and the API
2. Run `python src/gui.py` and inspect the "Neuromodulators:" block on the side panel

### If thirty minutes are available

Read:

1. **[NEUROMODULATORS_SUMMARY_REPORT.md](NEUROMODULATORS_SUMMARY_REPORT.en.md)** — an overview of the implementation
2. **[NEUROMODULATORS_QUICK_REFERENCE.md](NEUROMODULATORS_QUICK_REFERENCE.en.md)** — code examples

### If a developer needs the full account (60 minutes or more)

Read in this order:

1. **[NEUROMODULATORS_SUMMARY_REPORT.md](NEUROMODULATORS_SUMMARY_REPORT.en.md)** (15 min) — overview
2. **[NEUROMODULATORS_IMPLEMENTATION.md](NEUROMODULATORS_IMPLEMENTATION.en.md)** (30 min) — architecture
3. **[NEUROMODULATORS_QUICK_REFERENCE.md](NEUROMODULATORS_QUICK_REFERENCE.en.md)** (20 min) — examples and API
4. **[NEUROMODULATORS_FULL_REPORT.md](NEUROMODULATORS_FULL_REPORT.en.md)** (30 min) — the full report with metrics

---

## Structure of the documentation

### Principal documents (new, February 2026)

| Document | Size | Purpose | Audience |
|----------|--------|-----------|-----------|
| **NEUROMODULATORS_QUICK_REFERENCE.md** | 10 pp. | Short reference with examples | All developers |
| **NEUROMODULATORS_IMPLEMENTATION.md** | 12 pp. | Full technical specification | Technical leads, architects |
| **NEUROMODULATORS_SUMMARY_REPORT.md** | 8 pp. | Summary report of the changes | Project managers, developers |
| **NEUROMODULATORS_FULL_REPORT.md** | 18 pp. | Detailed report with metrics | Developers, analysts |

### Supporting documents

| Document | Size | Purpose |
|----------|--------|-----------|
| **README.md** | 3 pp. | Main page of the project |
| **INDEX.md** | 15 pp. | Full index of all documentation |
| **CHANGELOG.md** | 20 pp. | History of project changes |

---

## What each document contains

### NEUROMODULATORS_QUICK_REFERENCE.md

```
├── Quick Lookup Table (краткие характеристики)
├── API Reference (методы и параметры)
├── Usage Examples (3 типовых сценария)
├── GUI Visualization Guide (как читать интерфейс)
├── Testing Guide (как писать тесты)
└── Troubleshooting (решение проблем)
```

**When to read:** a short reference or code examples are required

### NEUROMODULATORS_IMPLEMENTATION.md

```
├── Overview (что это и зачем)
├── Architecture (как всё устроено)
├── Components (каждый нейромодулятор подробно)
├── Integration (как подключить к своему коду)
├── Examples (примеры использования)
├── Testing (как тестируется)
├── Decisions (почему так сделано)
└── Future Enhancements (что дальше)
```

**When to read:** the principle of operation must be understood, or new functionality is to be added

### NEUROMODULATORS_SUMMARY_REPORT.md

```
├── Обзор системы
├── Архитектурные изменения
├── Файлы изменений (что добавлено/изменено)
├── Тестирование (результаты, ошибки)
├── Документация
├── Метрики проекта
├── Деплоймент (как развернуть)
└── Дальнейшее развитие
```

**When to read:** a full report of the work done is required

### NEUROMODULATORS_FULL_REPORT.md

```
├── Исходное техническое задание
├── Реализованная архитектура (детально)
├── Интеграция (пошаговая инструкция)
├── Тестирование (полные результаты)
├── Документация (структура)
├── Метрики (код, время, качество)
├── Деплоймент (чеклист)
└── Влияние на систему
```

**When to read:** complete control of every detail is required

---

## Examples of using the documentation

### Scenario 1: a new developer in the project

1. Read [README.md](README.md) — 5 minutes
2. Consult [QUICK_START_RU.md](QUICK_START_RU.en.md) — 15 minutes
3. Open [NEUROMODULATORS_QUICK_REFERENCE.md](NEUROMODULATORS_QUICK_REFERENCE.en.md) — 10 minutes
4. Run `python src/gui.py` and experiment — 10 minutes

**Total:** about 40 minutes, after which the basics are understood

### Scenario 2: a new neuromodulator must be added

1. Read [NEUROMODULATORS_IMPLEMENTATION.md](NEUROMODULATORS_IMPLEMENTATION.en.md) (section "Components") — 10 minutes
2. Consult the examples in the same document (section "Examples") — 5 minutes
3. Open `src/neuromodulators.py` and study the existing subclasses — 10 minutes
4. Read `tests/test_neuromodulators.py` in order to see how tests are written — 10 minutes

**Total:** about 35 minutes, after which code can be added

### Scenario 3: an error must be understood

1. Open [NEUROMODULATORS_QUICK_REFERENCE.md](NEUROMODULATORS_QUICK_REFERENCE.en.md) (section "Troubleshooting")
2. If that does not suffice, open [NEUROMODULATORS_FULL_REPORT.md](NEUROMODULATORS_FULL_REPORT.en.md) (section "Errors and their resolution")
3. If that still does not suffice, consult [INDEX.md](INDEX.en.md) for further reading

**Total:** depends on the complexity of the error; usually 15–30 minutes

---

## How to read code and documentation together

### Recommended procedure

1. **Open the document** in one window of the editor
2. **Open the code file** in another window
3. **Read the examples in the document**, comparing them with the actual code

### Files that correspond

| Document | Code file | Begin at |
|----------|-----------|----------|
| Section "API Reference" in QUICK_REFERENCE | `src/neuromodulators.py` | Class `NeuromodulatorState` |
| Section "Integration" in IMPLEMENTATION | `src/agent.py` | Line `from neuromodulators import` |
| Section "Sleep Effects" in IMPLEMENTATION | `src/sleep.py` | Method `_apply_neuromodulators_during_sleep()` |
| Section "Storage" in IMPLEMENTATION | `src/storage.py` | Function `save_agent()` |
| Section "GUI" in IMPLEMENTATION | `src/gui.py` | Search for "neuromodulator" or "da_label" |

---

## Test set for validation

Confirm that the following concepts are understood.

### Basic (required of everyone)

- [ ] Which 4 neuromodulators exist and what they do
- [ ] The value range [0.0, 1.0] and why it is that range
- [ ] The baseline level 0.1 and its meaning
- [ ] When effects are applied (only during sleep)
- [ ] Which signals update the neuromodulators (reward, novelty, conflict)

### Advanced (for developers)

- [ ] How exponential decay works (formula and parameters)
- [ ] The influence coefficients of each signal (0.2 DA, 0.3 NE, and so on)
- [ ] The 4 neuromodulator effects during sleep (which does what)
- [ ] Serialisation and deserialisation (to_dict/from_dict)
- [ ] Integration into Agent.step() and sleep_manager.sleep_cycle()

### Mastery (for architects)

- [ ] Why the system is separated from AffectiveState
- [ ] Why it is not applied during step()
- [ ] How to preserve backward compatibility with older saves
- [ ] How to extend the system with new modulators without breaking changes
- [ ] How to test effects (unit versus integration)

---

## Checklist for adoption

Before the system is used in production:

- [ ] The documentation has been read (the document appropriate to the role)
- [ ] The GUI has been run and the neuromodulators have been seen
- [ ] The tests have been run: `pytest tests/test_neuromodulators.py`
- [ ] The onboarding has been completed (if the reader is new to the project)
- [ ] An agent has been saved and loaded (persistence has been checked)
- [ ] Parameters in the code have been varied experimentally
- [ ] The integration with the rest of the system is understood

---

## Further resources

### If something in the documentation is unclear

1. **Search INDEX.md** — another point of view may be recorded there
2. **Consult the code examples** in NEUROMODULATORS_QUICK_REFERENCE.md
3. **Open the source** — comments are often present there
4. **Run the GUI in debug mode** and observe how the values change

### Useful commands

```bash
# Запустить интерактивный режим Python
python

# Импортировать и протестировать
from src.neuromodulators import NeuromodulatorState
nm = NeuromodulatorState()
nm.update_from_signals(reward=0.5, novelty=0, conflict=0)
print(nm.snapshot())

# Запустить тесты с verbose output
pytest tests/test_neuromodulators.py -v

# Запустить GUI
python src/gui.py

# Посмотреть, как сохраняются нейромодуляторы
python -c "import json; from storage import read_agent_state; print(json.dumps(read_agent_state('saves/agent_save.nowa').get('neuromodulators'), indent=2))"
```

---

## Updates of the documentation

This documentation is current as of:

- **Date of creation:** 5 February 2026
- **Code version:** 2.0
- **Status:** complete

When the code is updated, update the documentation in the same pull request.

---

## Frequently asked questions

**Q: Where should one begin?**
A: A newcomer should read [QUICK_START_RU.md](QUICK_START_RU.en.md), then [NEUROMODULATORS_QUICK_REFERENCE.md](NEUROMODULATORS_QUICK_REFERENCE.en.md).

**Q: Must every document be read?**
A: No. Choose according to role (see "Quick navigation" above).

**Q: What if an error is found in the documentation?**
A: Correct it and open a pull request. The documentation is living and is expected to improve.

**Q: Which document is the most current?**
A: NEUROMODULATORS_IMPLEMENTATION.md — it holds the original specification.

**Q: How are the neuromodulators related to the affective system?**
A: They are different systems. The affective system is the current state of regulation; the neuromodulators modulate learning. See the section "Separation from Affect" in IMPLEMENTATION.

---

**Document:** documentation guide
**Version:** 1.0
**Date:** 5 February 2026
**Author:** NOWA Development Team
