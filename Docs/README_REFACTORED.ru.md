# NOWA-Cognitive: переработанная архитектура

English version: [README_REFACTORED.en.md](README_REFACTORED.en.md)

**Статус (27 сентября 2026 г.).** Документ ядра. Актуальное научное изложение комплекса на русском и английском языках приведено в [SCIENTIFIC_DESCRIPTION.ru.md](SCIENTIFIC_DESCRIPTION.ru.md). Текст ниже сохраняет формулировки исходной редакции: это нормативный контракт модуля либо лабораторная запись.

## Обзор

NOWA-Cognitive успешно переработан так, чтобы реализовать основной принцип:

> **Поведение не обучается. Оно возникает из опыта и консолидации.**

Это не система машинного обучения. Это когнитивная архитектура, в которой:

- опыты являются неизменяемыми историческими записями
- днём пишется ограниченный лабильный слой; стабильная память консолидируется только во сне
- поведение возникает из активации памяти, а не из оптимизации весов
- агент адаптируется дневными лабильными метками и ночной консолидацией

---

## Компоненты системы

### 1. **Событие и опыт**
Неизменяемые представления того, что происходит:

```python
# Create context
path = Path()
path = path.add_event(Event("user:hello", EventType.CONTEXT))
path = path.add_event(Event("action:greet", EventType.ACTION))

# Store as immutable experience
exp = Experience(path, consequence=result_event, intensity=1.0)
# Cannot modify exp.path after creation - it's frozen!
```

### 2. **Гиппокамп** (кратковременная память)
Хранит недавние опыты с затуханием по времени:

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

### 3. **Селектор** (выбор действия — необучаемый)
Принимает решения на основе давления опыта, а не весов:

```python
selector = ActionSelector(["greet", "ignore", "ask"], confidence_threshold=0.7)

# Choose action based on hippocampal and cortical input
# (selector has NO weights, NO learning, NO optimization)
action = selector.choose(hippocampal_exps, cortical_patterns)
```

**Как устроен выбор:**

1. Вычислить «давление» из интенсивности гиппокампального опыта
2. Добавить смещение от корковых паттернов
3. Вычислить уверенность = максимальное давление / суммарное давление
4. Если уверенность выше порога: детерминированный выбор (лучший вариант)
5. Если уверенность не выше порога: стохастический выбор (исследование)

### 4. **Менеджер сна** (консолидация стабильного слоя)
Консолидирует опыты в абстрактные паттерны:

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

### 5. **Кора** (долговременная память)
Медленная память абстрактных паттернов — изменяется только во время сна:

```python
from sleep import CortexMemory

cortex = CortexMemory()

# Patterns stored during sleep consolidation (not during waking!)
pattern = cortex.store_pattern(("context", "action:greet"))

# Activate patterns in context
active_patterns = cortex.activate(["user:hello"])
```

### 6. **Агент** (система)
Объединяет все компоненты:

```python
agent = Agent(hippocampus, cortex, selector, sleep_manager=sleep_manager)

# Бодрствование: эпизоды + лабильные смещения Q/Go/NoGo при известной награде
action = agent.step(["user:hello"], consequence=result_event, intensity=1.0)

# Сон: стабильные Q, каналы, привычки, кора
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

## Пример: полный цикл бодрствование–сон–бодрствование

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

## Ключевые принципы

### Что разрешено

- Хранение опытов (неизменяемых)
- Затухание энергии активации по времени
- Активация опыта по контексту
- Консолидация паттернов во сне
- Выбор по уверенности со стохастичностью
- Естественное забывание неустойчивых воспоминаний

### Что запрещено

- Оптимизация весов селектора
- Вычисление потерь и точности
- Эпохи обучения
- Накопление вознаграждения
- Прямое изменение поведения
- Любое обучение вне сна

---

## Тестирование

Все 66 тестов проходят:

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

## Структура файлов

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

## Диаграмма архитектуры

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

## Принцип NOWA

**Вопрос:** если селектор заморожен, а агент получает новый опыт, изменится ли поведение?

**Ответ NOWA:** да, через консолидацию во сне.

- Новые опыты активируются в гиппокампе
- Сон группирует и консолидирует их
- Корковые паттерны сдвигаются
- Давление выбора меняется
- Поведение возникает иным

**Ответ машинного обучения:** возможно. Это зависит от оптимизации весов во время обучения.

**В этом фундаментальное различие:** NOWA меняет поведение через консолидацию опыта, а не через оптимизацию параметров.

---

## Переход от старого кода

Если использовался прежний `SelectorTrainer`:

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

## Документация

- [REFACTORING_COMPLETE.md](REFACTORING_COMPLETE.ru.md) — подробный отчёт о переработке
- [nowa_refactoring_plan_v_2.md](nowa_refactoring_plan_v_2.ru.md) — исходный план переработки
- [CHANGELOG.md](CHANGELOG.ru.md) — история версий

---

## Дальнейшая разработка

Переработанная архитектура готова к:

- обработке естественного языка (NOWA NLP)
- многоагентным системам
- исследованиям долговременной памяти
- исследованиям возникновения поведения
- когнитивному моделированию

Всё это — в пределах принципа: **поведение возникает, а не обучается.**

---

**Статус:** готовность к эксплуатации — все тесты проходят, архитектура проверена
